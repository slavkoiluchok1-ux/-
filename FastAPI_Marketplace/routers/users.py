from __future__ import annotations

import io
import os
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot import generate_unique_tg_link_code
from database import get_db
from dependencies import get_current_user
from models import Product, User

router = APIRouter(prefix="/api/v1", tags=["users"])
BASE_DIR = Path(__file__).resolve().parents[1]
AVATAR_DIR = BASE_DIR / "static" / "uploads" / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_AVATAR_SIZE_BYTES = 2 * 1024 * 1024


def _avatar_file_path(avatar_url: str | None) -> Path | None:
    if not avatar_url:
        return None
    cleaned = avatar_url.strip()
    if not cleaned.startswith("/static/"):
        return None
    relative = cleaned.lstrip("/")
    return (BASE_DIR / relative).resolve()


async def _validate_avatar_upload(file: UploadFile) -> tuple[bytes, str]:
    if file.filename is None or not file.filename.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл аватарки не вказано.")

    filename = file.filename.strip()
    extension = Path(filename).suffix.lower()
    content_type = (file.content_type or "").lower()

    if content_type not in ALLOWED_MIME_TYPES or extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Дозволені тільки JPG, JPEG, PNG або WEBP.")

    data = await file.read()
    if len(data) == 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл порожній.")
    if len(data) > MAX_AVATAR_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Розмір аватарки не повинен перевищувати 2 МБ.")

    try:
        with Image.open(io.BytesIO(data)) as image:
            image.verify()
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            detected_format = image.format or ""
            if detected_format.upper() not in {"JPEG", "PNG", "WEBP"}:
                raise ValueError("Unsupported image format")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недійсний файл зображення.") from exc

    return data, extension


@router.get("/users/{user_id}/public-profile")
async def get_public_profile(
    user_id: int,
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Користувача не знайдено")

    if not user.telegram_chat_id and not user.tg_link_code:
        user.tg_link_code = await generate_unique_tg_link_code(db)
        await db.commit()

    stmt = select(Product).where(Product.user_id == user_id).order_by(Product.created_at.desc())
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        stmt = stmt.where((Product.title.ilike(pattern)) | (Product.description.ilike(pattern)))

    stmt = stmt.options(selectinload(Product.media))
    result = await db.execute(stmt)
    products = result.scalars().all()

    display_name = " ".join(
        part for part in [user.first_name, user.last_name] if part and part.strip()
    ).strip() or user.username

    return {
        "id": user.id,
        "first_name": user.first_name or None,
        "last_name": user.last_name or None,
        "username": user.username,
        "display_name": display_name,
        "avatar_url": user.avatar_url,
        "tg_link_code": user.tg_link_code,
        "telegram_chat_id": user.telegram_chat_id,
        "products": [
            {
                "id": product.id,
                "title": product.title,
                "description": product.description,
                "price": product.price,
                "quantity": product.quantity,
                "seller_phone": product.seller_phone,
                "image_url": (
                    next((media.file_path for media in product.media if media.media_type == "photo"), None)
                    or (product.media[0].file_path if product.media else None)
                ),
            }
            for product in products
        ],
    }


@router.post("/users/me/avatar")
async def upload_user_avatar(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data, extension = await _validate_avatar_upload(file)

    if current_user.avatar_url:
        old_path = _avatar_file_path(current_user.avatar_url)
        if old_path and old_path.exists() and old_path.is_file():
            try:
                old_path.unlink()
            except OSError:
                pass

    safe_ext = ".jpg" if extension.lower() in {".jpg", ".jpeg"} else extension.lower()
    filename = f"{uuid.uuid4()}{safe_ext}"
    avatar_path = AVATAR_DIR / filename
    avatar_path.write_bytes(data)

    current_user.avatar_url = f"/static/uploads/avatars/{filename}"
    await db.commit()
    await db.refresh(current_user)

    return {"success": True, "avatar_url": current_user.avatar_url}


@router.delete("/users/me/avatar")
async def delete_user_avatar(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.avatar_url:
        old_path = _avatar_file_path(current_user.avatar_url)
        if old_path and old_path.exists() and old_path.is_file():
            try:
                old_path.unlink()
            except OSError:
                pass
        current_user.avatar_url = None
        await db.commit()
        await db.refresh(current_user)

    return {"success": True, "avatar_url": None}


@router.post("/users/unbind-telegram")
async def unbind_telegram(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.telegram_chat_id = None
    current_user.tg_link_code = current_user.tg_link_code or await generate_unique_tg_link_code(db)
    await db.commit()
    await db.refresh(current_user)
    return {
        "success": True,
        "tg_link_code": current_user.tg_link_code,
        "telegram_chat_id": current_user.telegram_chat_id,
    }
