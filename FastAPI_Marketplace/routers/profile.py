from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import decode_access_token
from bot import ensure_user_tg_link_code
from database import get_db
from dependencies import get_current_user
from models import Order, OrderItem, Product, User

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="Templates")


async def _user_has_sales(db: AsyncSession, user_id: int) -> bool:
    result = await db.execute(
        select(OrderItem.id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Product.user_id == user_id)
        .where(Order.status != "cancelled")
        .limit(1)
    )
    return result.scalar() is not None


def _user_role_label(user: User) -> str:
    if user.is_superuser:
        return "Суперадмін"
    if user.is_admin:
        return "Адміністратор"
    return "Користувач"


@router.get("/profile", response_class=HTMLResponse)
async def profile_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    current_user = None
    token_value = request.cookies.get("access_token")
    if token_value:
        try:
            payload = decode_access_token(token_value.replace("Bearer ", "").strip())
            user_id = payload.get("sub")
            if user_id is not None:
                current_user = await db.get(User, int(user_id))
        except Exception:
            current_user = None

    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    await ensure_user_tg_link_code(current_user, db)
    has_sales = await _user_has_sales(db, current_user.id)

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "current_user": current_user,
            "has_sales": has_sales,
            "user_role": _user_role_label(current_user),
            "profile_message": request.query_params.get("message"),
            "profile_error": request.query_params.get("error"),
            "telegram_bot_link": "https://t.me/FastMoneyMarketBot",
        },
    )


@router.post("/profile")
async def update_profile(
    first_name: str = Form(default=""),
    last_name: str = Form(default=""),
    birth_date: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.first_name = first_name.strip() or None
    current_user.last_name = last_name.strip() or None

    if birth_date:
        try:
            parsed_birth_date = datetime.strptime(birth_date, "%Y-%m-%d").date()
            current_user.birth_date = parsed_birth_date
        except ValueError:
            return RedirectResponse(url="/profile?error=Невірний+формат+дати+народження", status_code=status.HTTP_303_SEE_OTHER)
    else:
        current_user.birth_date = current_user.birth_date

    if current_user.birth_date is not None:
        today = datetime.utcnow().date()
        age = today.year - current_user.birth_date.year - ((today.month, today.day) < (current_user.birth_date.month, current_user.birth_date.day))
        current_user.is_age_locked = age < 18
    else:
        current_user.is_age_locked = False

    current_user.display_name = " ".join(
        part for part in [current_user.first_name, current_user.last_name] if part and part.strip()
    ).strip() or current_user.username

    await db.commit()
    return RedirectResponse(url="/profile?message=Дані+акаунту+оновлено", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/v1/users/me/birth-date")
async def update_current_user_birth_date(
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload is None:
        payload = {}

    birth_date_value = payload.get("birth_date")
    if birth_date_value in (None, ""):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Birth date is required")

    try:
        parsed_birth_date = datetime.strptime(str(birth_date_value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid birth date format") from exc

    current_user.birth_date = parsed_birth_date
    today = datetime.utcnow().date()
    age = today.year - current_user.birth_date.year - ((today.month, today.day) < (current_user.birth_date.month, current_user.birth_date.day))
    current_user.is_age_locked = age < 18
    current_user.display_name = " ".join(
        part for part in [current_user.first_name, current_user.last_name] if part and part.strip()
    ).strip() or current_user.username

    await db.commit()
    await db.refresh(current_user)
    return {
        "success": True,
        "birth_date": current_user.birth_date.isoformat(),
        "is_age_locked": current_user.is_age_locked,
    }


@router.put("/api/v1/users/me")
@router.post("/api/v1/users/me")
async def update_current_user_profile(
    payload: dict | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if payload is None:
        payload = {}

    first_name = str(payload.get("first_name", current_user.first_name or "")).strip() if payload.get("first_name") is not None else current_user.first_name
    last_name = str(payload.get("last_name", current_user.last_name or "")).strip() if payload.get("last_name") is not None else current_user.last_name

    current_user.first_name = first_name or None
    current_user.last_name = last_name or None
    current_user.display_name = " ".join(
        part for part in [current_user.first_name, current_user.last_name] if part and part.strip()
    ).strip() or current_user.username

    await db.commit()
    await db.refresh(current_user)
    return {
        "id": current_user.id,
        "username": current_user.username,
        "email": current_user.email,
        "first_name": current_user.first_name,
        "last_name": current_user.last_name,
        "display_name": current_user.display_name,
    }


@router.post("/profile/password")
async def change_password(
    current_password: str = Form(...),
    new_password: str = Form(...),
    confirm_password: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not current_user.verify_password(current_password):
        return RedirectResponse(url="/profile?error=Невірний+поточний+пароль", status_code=status.HTTP_303_SEE_OTHER)

    if len(new_password) < 6:
        return RedirectResponse(url="/profile?error=Новий+пароль+має+містити+щонайменше+6+символів", status_code=status.HTTP_303_SEE_OTHER)

    if new_password != confirm_password:
        return RedirectResponse(url="/profile?error=Паролі+не+співпадають", status_code=status.HTTP_303_SEE_OTHER)

    current_user.set_password(new_password)
    await db.commit()
    return RedirectResponse(url="/profile?message=Пароль+успішно+змінено", status_code=status.HTTP_303_SEE_OTHER)
