from __future__ import annotations

from typing import Annotated
from urllib.parse import urlencode

from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from auth_utils import decode_access_token
from database import get_db
from models import User

security = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None,
) -> str | None:
    if credentials is not None and credentials.credentials:
        return credentials.credentials
    cookie_value = request.cookies.get("access_token")
    if cookie_value:
        return cookie_value.replace("Bearer ", "").strip()
    return None


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: AsyncSession = Depends(get_db),
) -> User:
    token_value = _extract_token(request, credentials)

    if token_value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required")

    payload = decode_access_token(token_value)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is missing user id")

    user = await db.get(User, int(user_id))
    if user is None or not user.is_active or getattr(user, "is_banned", False):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_optional_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: AsyncSession = Depends(get_db),
) -> User | None:
    token_value = _extract_token(request, credentials)

    if token_value is None:
        return None

    try:
        payload = decode_access_token(token_value)
    except HTTPException:
        return None

    user_id = payload.get("sub")
    if user_id is None:
        return None

    user = await db.get(User, int(user_id))
    if user is None or not user.is_active or getattr(user, "is_banned", False):
        return None
    return user


def _build_login_redirect(request: Request) -> RedirectResponse:
    next_url = request.url.path
    if request.url.query:
        next_url = f"{next_url}?{request.url.query}"
    login_url = "/login"
    if next_url and next_url != "/login" and next_url != "/register":
        login_url = f"{login_url}?{urlencode({'next': next_url})}"
    return RedirectResponse(url=login_url, status_code=status.HTTP_303_SEE_OTHER)


async def get_current_user_or_redirect(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)] = None,
    db: AsyncSession = Depends(get_db),
) -> User | RedirectResponse:
    token_value = _extract_token(request, credentials)

    if token_value is None:
        return _build_login_redirect(request)

    try:
        payload = decode_access_token(token_value)
    except HTTPException:
        return _build_login_redirect(request)

    user_id = payload.get("sub")
    if user_id is None:
        return _build_login_redirect(request)

    user = await db.get(User, int(user_id))
    if user is None or not user.is_active or getattr(user, "is_banned", False):
        return _build_login_redirect(request)
    return user


async def get_current_admin_user(current_user: User = Depends(get_current_user)) -> User:
    if not (current_user.is_admin or current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_current_admin_or_redirect(
    current_user_or_redirect: User | RedirectResponse = Depends(get_current_user_or_redirect),
) -> User | RedirectResponse:
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect
    if not (current_user_or_redirect.is_admin or current_user_or_redirect.is_superuser):
        return _build_login_redirect_for_role(current_user_or_redirect)
    return current_user_or_redirect


def _build_login_redirect_for_role(current_user: User) -> RedirectResponse:
    return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser access required")
    return current_user


async def get_current_superuser_or_redirect(
    current_user_or_redirect: User | RedirectResponse = Depends(get_current_user_or_redirect),
) -> User | RedirectResponse:
    if isinstance(current_user_or_redirect, RedirectResponse):
        return current_user_or_redirect
    if not current_user_or_redirect.is_superuser:
        return _build_login_redirect_for_role(current_user_or_redirect)
    return current_user_or_redirect
