from __future__ import annotations

from fastapi import APIRouter, Depends, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import User

router = APIRouter(tags=["profile"])
templates = Jinja2Templates(directory="Templates")


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

    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "request": request,
            "current_user": current_user,
            "user_role": _user_role_label(current_user),
            "profile_message": request.query_params.get("message"),
            "profile_error": request.query_params.get("error"),
        },
    )


@router.post("/profile")
async def update_profile(
    display_name: str = Form(default=""),
    email: str = Form(...),
    username: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cleaned_email = email.strip().lower()
    cleaned_username = username.strip()

    if not cleaned_username:
        return RedirectResponse(url="/profile?error=Ім%27я+користувача+не+може+бути+порожнім", status_code=status.HTTP_303_SEE_OTHER)

    if not cleaned_email:
        return RedirectResponse(url="/profile?error=Email+не+може+бути+порожнім", status_code=status.HTTP_303_SEE_OTHER)

    conflict = await db.scalar(
        select(User).where(
            User.id != current_user.id,
            or_(User.email == cleaned_email, User.username == cleaned_username),
        )
    )
    if conflict:
        return RedirectResponse(url="/profile?error=Email+або+username+вже+зайняті", status_code=status.HTTP_303_SEE_OTHER)

    current_user.display_name = display_name.strip() or None
    current_user.email = cleaned_email
    current_user.username = cleaned_username

    await db.commit()
    return RedirectResponse(url="/profile?message=Дані+акаунту+оновлено", status_code=status.HTTP_303_SEE_OTHER)


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
