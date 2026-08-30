from __future__ import annotations

import secrets
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from datetime import datetime, timezone

from auth_utils import create_access_token
from bot import send_telegram_notification
from database import get_db
from models import User
from schemas import Token, UserCreate, UserLogin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "Templates"))


def issue_csrf_cookie(response: JSONResponse | RedirectResponse) -> str:
    token = secrets.token_urlsafe(32)
    response.set_cookie(
        key="csrf_token",
        value=token,
        httponly=False,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24,
        path="/",
    )
    return token


@router.get("/csrf")
async def csrf_token_endpoint() -> JSONResponse:
    response = JSONResponse(content={"csrf_token": secrets.token_urlsafe(32)})
    issue_csrf_cookie(response)
    return response


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    existing_user = await db.scalar(
        select(User).where((User.email == payload.email.lower()) | (User.username == payload.username))
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Користувач з таким email або логіном вже існує")

    birth_date = payload.birth_date
    is_age_locked = False
    if birth_date is not None:
        today = date.today()
        age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
        if age < 18:
            is_age_locked = True

    user = User(
        username=payload.username,
        email=payload.email.lower(),
        first_name=payload.first_name,
        last_name=payload.last_name,
        birth_date=birth_date,
        is_age_locked=is_age_locked,
        display_name=(payload.first_name or payload.last_name or payload.username),
        is_active=True,
        is_superuser=False,
        is_admin=False,
    )
    user.set_password(payload.password)
    db.add(user)
    await db.commit()
    await db.refresh(user)

    access_token = create_access_token(user.id)
    response = JSONResponse(
        content={
            "status": "success",
            "message": "Реєстрація успішна",
            "redirect_url": "/",
            "access_token": access_token,
            "token_type": "bearer",
        }
    )
    issue_csrf_cookie(response)
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        secure=False,
        max_age=60 * 60 * 24,
        path="/",
    )
    return response


async def _parse_login_credentials(request: Request) -> tuple[str, str]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірний формат даних для входу")
        identifier = str(payload.get("email") or payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
    else:
        form = await request.form()
        identifier = str(form.get("email") or form.get("username") or "").strip()
        password = str(form.get("password") or "")

    if not identifier or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Відсутні дані для входу")

    return identifier, password


@router.post("/login")
async def login_user(request: Request, db: AsyncSession = Depends(get_db)):
    content_type = request.headers.get("content-type", "").lower()
    identifier, password = await _parse_login_credentials(request)

    user = await db.scalar(
        select(User).where(or_(User.email == identifier.lower(), User.username == identifier))
    )
    if user is None or not user.verify_password(password):
        if "application/json" not in content_type:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"request": request, "current_user": None, "error": "Невірний логін або пароль"},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        if "application/json" not in content_type:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"request": request, "current_user": None, "error": "Обліковий запис деактивовано"},
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    if user.birth_date is None:
        if "application/json" not in content_type:
            return templates.TemplateResponse(
                request,
                "login.html",
                {
                    "request": request,
                    "current_user": None,
                    "error": "Для входу потрібно вказати дату народження",
                    "require_birth_date": True,
                },
            )
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Birth date is required")

    access_token = create_access_token(user.id)
    redirect_url = "/admin" if (user.is_superuser or user.is_admin) else "/"

    client_ip = request.client.host if request.client else None
    if client_ip and user.telegram_chat_id:
        if user.last_login_ip and user.last_login_ip != client_ip:
            timestamp = datetime.now(timezone.utc).strftime("%d.%m.%Y %H:%M:%S UTC")
            await send_telegram_notification(user.telegram_chat_id, f"🔐 Вхід у ваш акаунт з нового пристрою {timestamp}")
        user.last_login_ip = client_ip
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()
    elif client_ip:
        user.last_login_ip = client_ip
        user.last_login_at = datetime.now(timezone.utc)
        await db.commit()

    cookie_kwargs = {
        "key": "access_token",
        "value": f"Bearer {access_token}",
        "httponly": True,
        "samesite": "lax",
        "max_age": 60 * 60 * 24,
        "path": "/",
    }

    if "application/json" in content_type:
        response = JSONResponse(content={
            "access_token": access_token,
            "token_type": "bearer",
            "is_admin": bool(user.is_admin),
            "is_superuser": bool(user.is_superuser),
            "redirect_url": redirect_url,
        })
        issue_csrf_cookie(response)
        response.set_cookie(**cookie_kwargs)
        return response

    redirect = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    issue_csrf_cookie(redirect)
    redirect.set_cookie(**cookie_kwargs)
    return redirect


@router.post("/logout")
@router.get("/logout")
async def logout_user(response: Response):
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key="access_token", path="/")
    redirect.delete_cookie(key="csrf_token", path="/")
    redirect.delete_cookie(key="session", path="/")
    return redirect
