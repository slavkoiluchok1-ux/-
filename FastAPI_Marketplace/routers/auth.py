from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import create_access_token
from database import get_db
from models import User
from schemas import Token, UserCreate, UserLogin

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])
BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "Templates"))


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_user(payload: UserCreate, request: Request, db: AsyncSession = Depends(get_db)):
    existing_user = await db.scalar(
        select(User).where((User.email == payload.email.lower()) | (User.username == payload.username))
    )
    if existing_user:
        raise HTTPException(status_code=400, detail="Користувач з таким email або логіном вже існує")

    user = User(
        username=payload.username,
        email=payload.email.lower(),
        display_name=payload.username,
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
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,
        path="/",
    )
    return response


async def _parse_login_credentials(request: Request) -> tuple[str, str, str | None]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірний формат даних для входу")
        identifier = str(payload.get("email") or payload.get("username") or "").strip()
        password = str(payload.get("password") or "")
        next_param = str(payload.get("next") or "").strip() or None
    else:
        form = await request.form()
        identifier = str(form.get("email") or form.get("username") or "").strip()
        password = str(form.get("password") or "")
        next_param = str(form.get("next") or "").strip() or None

    if not identifier or not password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Відсутні дані для входу")

    return identifier, password, next_param


@router.post("/login")
async def login_user(request: Request, db: AsyncSession = Depends(get_db)):
    content_type = request.headers.get("content-type", "").lower()
    identifier, password, next_param = await _parse_login_credentials(request)

    user = await db.scalar(
        select(User).where(or_(User.email == identifier.lower(), User.username == identifier))
    )
    if user is None or not user.verify_password(password):
        if "application/json" not in content_type:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"request": request, "current_user": None, "error": "Невірний логін або пароль", "next": next_param or ""},
            )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")
    if not user.is_active:
        if "application/json" not in content_type:
            return templates.TemplateResponse(
                request,
                "login.html",
                {"request": request, "current_user": None, "error": "Обліковий запис деактивовано", "next": next_param or ""},
            )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User is inactive")

    access_token = create_access_token(user.id)

    default_redirect = "/admin" if (user.is_superuser or user.is_admin) else "/"
    if next_param and not (user.is_superuser or user.is_admin):
        redirect_url = next_param
    else:
        redirect_url = default_redirect

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
        response.set_cookie(**cookie_kwargs)
        return response

    redirect = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(**cookie_kwargs)
    return redirect


@router.post("/logout")
@router.get("/logout")
async def logout_user(response: Response):
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key="access_token", path="/")
    redirect.delete_cookie(key="session", path="/")
    return redirect
