from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import Favorite, Product, User
from schemas import FavoriteOut, MessageResponse, ProductListOut

router = APIRouter(tags=["favorites"])
templates = Jinja2Templates(directory="Templates")


@router.get("/favorites", response_class=HTMLResponse)
async def favorites_page(request: Request, db: AsyncSession = Depends(get_db)):
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
        "favorites.html",
        {"request": request, "current_user": current_user, "is_authenticated": current_user is not None},
    )


@router.get("/api/v1/favorites", response_model=list[FavoriteOut])
async def get_favorites(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    favorites = (
        await db.execute(select(Favorite).where(Favorite.user_id == current_user.id).order_by(Favorite.id.desc()))
    ).scalars().all()

    result: list[FavoriteOut] = []
    for favorite in favorites:
        product = await db.get(Product, favorite.product_id, options=[selectinload(Product.media)])
        if product is None:
            continue

        first_media = None
        if product.media and len(product.media) > 0:
            first_media = product.media[0].file_path

        result.append(
            FavoriteOut(
                id=favorite.id,
                user_id=favorite.user_id,
                product_id=favorite.product_id,
                product=ProductListOut(
                    id=product.id,
                    title=product.title,
                    description=product.description,
                    price=product.price,
                    quantity=product.quantity,
                    stock=product.quantity,
                    in_stock=product.quantity > 0,
                    is_available=product.quantity > 0,
                    seller_phone=product.seller_phone,
                    user_id=product.user_id,
                    sales_count=product.sales_count,
                    created_at=product.created_at,
                    media=[],
                    image_url=first_media,
                    average_rating=0.0,
                ),
            )
        )
    return result


@router.post("/api/v1/favorites/toggle/{product_id}", response_model=MessageResponse)
@router.post("/api/v1/favorites/{product_id}", response_model=MessageResponse)
async def toggle_favorite(product_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Товар не знайдено")

    favorite = await db.scalar(
        select(Favorite).where(and_(Favorite.user_id == current_user.id, Favorite.product_id == product_id))
    )
    if favorite:
        await db.delete(favorite)
        await db.commit()
        return {"message": "Товар видалено з обраного", "action": "removed"}

    fav = Favorite(user_id=current_user.id, product_id=product_id)
    db.add(fav)
    await db.commit()
    await db.refresh(fav)
    return {"message": "Товар додано до обраного", "action": "added", "id": fav.id}


@router.delete("/api/v1/favorites/{product_id}", response_model=MessageResponse)
async def remove_favorite(product_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    favorite = await db.scalar(
        select(Favorite).where(and_(Favorite.user_id == current_user.id, Favorite.product_id == product_id))
    )
    if not favorite:
        raise HTTPException(status_code=404, detail="Товар не знайдено в обраному")

    await db.delete(favorite)
    await db.commit()
    return MessageResponse(message="Товар видалено з обраного")
