from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user
from models import CartItem, Favorite, Product, ProductMedia, Review, ReviewMedia, User
from schemas import ProductCreate, ProductMediaResponse, ProductResponse, ReviewCreate, ReviewMediaResponse, ReviewResponse

router = APIRouter(tags=["catalog"])

templates = Jinja2Templates(directory="Templates")
MAX_UPLOAD_SIZE_BYTES = 1_073_741_824
UPLOAD_ROOT = Path(__file__).resolve().parents[1] / "static" / "uploads"
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def _normalize_media_type(file: UploadFile) -> str:
    content_type = (file.content_type or "").lower()
    filename = (file.filename or "").lower()
    is_image = content_type.startswith("image/") or any(filename.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"])
    is_video = content_type.startswith("video/") or any(filename.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"])
    if is_image:
        return "photo"
    if is_video:
        return "video"
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Помилка: виберіть правильне фото або відео.")


async def _save_uploaded_media(file: UploadFile) -> str:
    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Файл {file.filename or 'без назви'} перевищує допустимий розмір 1 ГБ.",
        )

    media_type = _normalize_media_type(file)
    extension = Path(file.filename or "upload.bin").suffix or (".jpg" if media_type == "photo" else ".mp4")
    unique_name = f"{uuid.uuid4()}_{Path(file.filename or 'upload').name.replace(Path(file.filename or 'upload').name, Path(file.filename or 'upload').stem)}{extension}"
    save_path = UPLOAD_ROOT / unique_name
    save_path.write_bytes(file_bytes)
    return f"/static/uploads/{unique_name}", media_type


async def _product_response_with_media(db: AsyncSession, product: Product) -> ProductResponse:
    media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
    media = [
        ProductMediaResponse(
            id=item.id,
            product_id=item.product_id,
            file_path=item.file_path,
            media_type=item.media_type,
        )
        for item in media_rows
    ]
    return ProductResponse(
        id=product.id,
        title=product.title,
        description=product.description,
        price=product.price,
        quantity=product.quantity,
        seller_phone=product.seller_phone,
        user_id=product.user_id,
        sales_count=product.sales_count,
        created_at=product.created_at,
        media=media,
    )


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(request: Request, q: str | None = None, db: AsyncSession = Depends(get_db)):
    current_user = None
    token_value = request.cookies.get("access_token")
    if token_value:
        try:
            from auth_utils import decode_access_token
            payload = decode_access_token(token_value.replace("Bearer ", "").strip())
            user_id = payload.get("sub")
            if user_id is not None:
                current_user = await db.get(User, int(user_id))
        except Exception:
            current_user = None

    stmt = select(Product).where(Product.quantity > 0)
    if q and q.strip():
        term = q.strip().lower()
        stmt = stmt.where(
            (func.lower(Product.title).contains(term)) | (func.lower(Product.description).contains(term))
        )
        stmt = stmt.order_by(
            case(
                (func.lower(Product.title).contains(term), 0),
                (func.lower(Product.description).contains(term), 1),
                else_=2,
            ),
            Product.sales_count.desc(),
            Product.created_at.desc(),
        )
    else:
        stmt = stmt.order_by(Product.sales_count.desc(), Product.created_at.desc())

    result = await db.execute(stmt)
    products = result.scalars().all()
    catalog_products = []
    for product in products:
        media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
        first_image = media_rows[0].file_path if media_rows else None
        catalog_products.append(
            {
                "id": product.id,
                "title": product.title,
                "description": product.description,
                "price": product.price,
                "quantity": product.quantity,
                "seller_phone": product.seller_phone,
                "image_url": first_image,
                "sales_count": product.sales_count,
                "created_at": product.created_at,
            }
        )

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "request": request,
            "current_user": current_user,
            "products": catalog_products,
            "q": q or "",
        },
    )


@router.get("/api/v1/products", response_model=list[ProductResponse])
async def list_products(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product).where(Product.quantity > 0)
    if q and q.strip():
        term = q.strip().lower()
        stmt = stmt.where((func.lower(Product.title).contains(term)) | (func.lower(Product.description).contains(term)))
        stmt = stmt.order_by(
            case(
                (func.lower(Product.title).contains(term), 0),
                (func.lower(Product.description).contains(term), 1),
                else_=2,
            ),
            Product.sales_count.desc(),
            Product.created_at.desc(),
        )
    else:
        stmt = stmt.order_by(Product.sales_count.desc(), Product.created_at.desc())

    result = await db.execute(stmt)
    products = result.scalars().all()
    return [await _product_response_with_media(db, product) for product in products]


@router.get("/products/{product_id}", response_class=HTMLResponse)
@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail_page(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")

    current_user = None
    token_value = request.cookies.get("access_token")
    if token_value:
        try:
            from auth_utils import decode_access_token
            payload = decode_access_token(token_value.replace("Bearer ", "").strip())
            user_id = payload.get("sub")
            if user_id is not None:
                current_user = await db.get(User, int(user_id))
        except Exception:
            current_user = None

    seller = await db.get(User, product.user_id)
    media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
    reviews = (await db.execute(select(Review).where(Review.product_id == product.id).order_by(Review.created_at.desc()))).scalars().all()

    review_items = []
    total_rating = 0
    for review in reviews:
        review_media = (await db.execute(select(ReviewMedia).where(ReviewMedia.review_id == review.id))).scalars().all()
        review_items.append({
            "id": review.id,
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at,
            "username": (await db.get(User, review.user_id)).username if await db.get(User, review.user_id) else None,
            "media": [
                ReviewMediaResponse(
                    id=item.id,
                    review_id=item.review_id,
                    file_path=item.file_path,
                    media_type=item.media_type,
                )
                for item in review_media
            ],
        })
        total_rating += review.rating

    average_rating = round(total_rating / len(reviews), 2) if reviews else 0.0

    return templates.TemplateResponse(
        request,
        "product_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "product": {
                "id": product.id,
                "title": product.title,
                "description": product.description,
                "price": product.price,
                "quantity": product.quantity,
                "seller_phone": product.seller_phone,
                "seller": seller,
                "media": [
                    {"id": item.id, "file_path": item.file_path, "media_type": item.media_type}
                    for item in media_rows
                ],
            },
            "seller": seller,
            "reviews": review_items,
            "average_rating": average_rating,
            "reviews_count": len(reviews),
        },
    )


@router.post("/api/v1/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    price: int = Form(...),
    quantity: int = Form(...),
    seller_phone: str | None = Form(default=None),
    files: list[UploadFile] = File(default_factory=list),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not title.strip() or not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Назва та опис товару обов'язкові.")

    final_phone = (seller_phone or current_user.phone or "").strip() or None

    product = Product(
        title=title.strip(),
        description=description.strip(),
        price=int(price),
        quantity=int(quantity),
        seller_phone=final_phone,
        user_id=current_user.id,
        sales_count=0,
    )
    db.add(product)
    await db.flush()

    for uploaded_file in files:
        if uploaded_file is None or not getattr(uploaded_file, "filename", None):
            continue
        if not uploaded_file.filename:
            continue
        file_path, media_type = await _save_uploaded_media(uploaded_file)
        db.add(ProductMedia(product_id=product.id, file_path=file_path, media_type=media_type))

    await db.commit()
    await db.refresh(product)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return await _product_response_with_media(db, product)

    if request.headers.get("accept", "").lower().startswith("application/json"):
        return await _product_response_with_media(db, product)

    return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/v1/products/{product_id}/reviews", response_model=ReviewResponse, status_code=status.HTTP_201_CREATED)
async def create_review(
    request: Request,
    product_id: int,
    rating: int = Form(...),
    comment: str | None = Form(default=None),
    files: list[UploadFile] = File(default_factory=list),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")
    if not 1 <= rating <= 5:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Оцінка має бути від 1 до 5.")

    review = Review(product_id=product_id, user_id=current_user.id, rating=rating, comment=(comment or "").strip() or None)
    db.add(review)
    await db.flush()

    for uploaded_file in files or []:
        if uploaded_file is None or not getattr(uploaded_file, "filename", None):
            continue
        if not uploaded_file.filename:
            continue
        file_bytes = await uploaded_file.read()
        if len(file_bytes) > MAX_UPLOAD_SIZE_BYTES:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Файл перевищує допустимий розмір 1 ГБ.")

        content_type = (uploaded_file.content_type or "").lower()
        filename = (uploaded_file.filename or "upload").lower()
        is_image = content_type.startswith("image/") or any(filename.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"])
        is_video = content_type.startswith("video/") or any(filename.endswith(ext) for ext in [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"])
        if not is_image and not is_video:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Помилка: виберіть правильне фото або відео.")

        media_type = "photo" if is_image else "video"
        extension = Path(uploaded_file.filename or "upload.bin").suffix or (".jpg" if media_type == "photo" else ".mp4")
        unique_name = f"{uuid.uuid4()}{extension}"
        target_path = UPLOAD_ROOT / unique_name
        target_path.write_bytes(file_bytes)
        db.add(ReviewMedia(review_id=review.id, file_path=f"/static/uploads/{unique_name}", media_type=media_type))

    await db.commit()
    await db.refresh(review)

    if request.headers.get("x-requested-with") == "XMLHttpRequest" or request.headers.get("accept", "").lower().startswith("application/json"):
        media_rows = (await db.execute(select(ReviewMedia).where(ReviewMedia.review_id == review.id))).scalars().all()
        return ReviewResponse(
            id=review.id,
            product_id=review.product_id,
            user_id=review.user_id,
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at,
            username=current_user.username,
            media=[
                ReviewMediaResponse(
                    id=item.id,
                    review_id=item.review_id,
                    file_path=item.file_path,
                    media_type=item.media_type,
                )
                for item in media_rows
            ],
        )
    return RedirectResponse(url=f"/product/{product_id}", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/api/v1/products/{product_id}/favorite", status_code=status.HTTP_200_OK)
async def toggle_favorite(product_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")

    existing = await db.scalar(select(Favorite).where(Favorite.user_id == current_user.id, Favorite.product_id == product_id))
    if existing:
        await db.delete(existing)
        await db.commit()
        return {"message": "Товар видалено з обраного"}

    db.add(Favorite(user_id=current_user.id, product_id=product_id))
    await db.commit()
    return {"message": "Товар додано до обраного"}


def _user_role(user: User | None) -> str:
    if user is None:
        return "guest"

    role_value = str(getattr(user, "role", "") or "").strip().lower()
    if role_value in {"admin", "superadmin"}:
        return role_value
    if getattr(user, "is_superuser", False):
        return "superadmin"
    if getattr(user, "is_admin", False):
        return "admin"
    return "user"


async def _get_current_user_from_request(request: Request, db: AsyncSession) -> User | None:
    token_value = request.cookies.get("access_token")
    if not token_value:
        return None
    try:
        from auth_utils import decode_access_token
        payload = decode_access_token(token_value.replace("Bearer ", "").strip())
        user_id = payload.get("sub")
        if user_id is None:
            return None
        user = await db.get(User, int(user_id))
        if user is None or not user.is_active:
            return None
        user.role = _user_role(user)
        return user
    except Exception:
        return None


@router.get("/my-products", response_class=HTMLResponse)
async def my_products_page(request: Request, db: AsyncSession = Depends(get_db)):
    token = request.cookies.get("access_token")
    current_user = None

    if token:
        try:
            from auth_utils import decode_access_token
            raw_token = token.replace("Bearer ", "").strip()
            payload = decode_access_token(raw_token)
            user_id = payload.get("sub")
            if user_id is not None:
                current_user = await db.get(User, int(user_id))
        except Exception:
            current_user = None

    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    stmt = (
        select(Product)
        .where(Product.user_id == current_user.id)
        .order_by(Product.created_at.desc())
    )
    products = (await db.execute(stmt)).scalars().all()

    my_products = []
    for product in products:
        media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
        first_image = media_rows[0].file_path if media_rows else None
        my_products.append({
            "id": product.id,
            "title": product.title,
            "description": product.description,
            "price": product.price,
            "quantity": product.quantity,
            "seller_phone": product.seller_phone,
            "image_url": first_image,
            "sales_count": product.sales_count,
            "created_at": product.created_at,
            "media_count": len(media_rows),
        })

    return templates.TemplateResponse(
        request,
        "my_products.html",
        {
            "request": request,
            "current_user": current_user,
            "products": my_products,
        },
    )


async def _ensure_product_owner(request: Request, product_id: int, db: AsyncSession) -> tuple[Product | None, User | None, RedirectResponse | None]:
    current_user = await _get_current_user_from_request(request, db)
    if current_user is None:
        return None, None, RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    current_user.role = _user_role(current_user)
    product = await db.get(Product, product_id)
    if product is None:
        return None, current_user, RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)

    if product.user_id != current_user.id and current_user.role not in {"admin", "superadmin"}:
        return None, current_user, RedirectResponse(url="/my-products", status_code=status.HTTP_303_SEE_OTHER)

    return product, current_user, None


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
async def edit_product_page(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    product, current_user, redirect = await _ensure_product_owner(request, product_id, db)
    if redirect is not None:
        return redirect

    media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
    return templates.TemplateResponse(
        request,
        "edit_product.html",
        {
            "request": request,
            "current_user": current_user,
            "product": {
                "id": product.id,
                "title": product.title,
                "description": product.description,
                "price": product.price,
                "quantity": product.quantity,
                "seller_phone": product.seller_phone,
                "media": [
                    {"id": m.id, "file_path": m.file_path, "media_type": m.media_type}
                    for m in media_rows
                ],
            },
        },
    )


@router.post("/products/{product_id}/edit", response_class=HTMLResponse)
async def edit_product_submit(
    request: Request,
    product_id: int,
    title: str = Form(...),
    description: str = Form(...),
    price: int = Form(...),
    quantity: int = Form(...),
    seller_phone: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
):
    product, current_user, redirect = await _ensure_product_owner(request, product_id, db)
    if redirect is not None:
        return redirect

    if not title.strip() or not description.strip():
        media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
        return templates.TemplateResponse(
            request,
            "edit_product.html",
            {
                "request": request,
                "current_user": current_user,
                "product": {
                    "id": product.id,
                    "title": title,
                    "description": description,
                    "price": price,
                    "quantity": quantity,
                    "seller_phone": seller_phone,
                    "media": [
                        {"id": m.id, "file_path": m.file_path, "media_type": m.media_type}
                        for m in media_rows
                    ],
                },
                "error": "Назва та опис товару обов'язкові.",
            },
        )

    product.title = title.strip()
    product.description = description.strip()
    try:
        product.price = int(price)
    except (TypeError, ValueError):
        product.price = 0
    try:
        product.quantity = int(quantity)
    except (TypeError, ValueError):
        product.quantity = 0
    product.seller_phone = (seller_phone or current_user.phone or "").strip() or None

    if file is not None and getattr(file, "filename", None):
        file_path, media_type = await _save_uploaded_media(file)
        db.add(ProductMedia(product_id=product.id, file_path=file_path, media_type=media_type))

    await db.commit()
    return RedirectResponse(url="/my-products", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/admin/products/{product_id}/delete")
@router.post("/products/{product_id}/delete")
async def delete_product_submit(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
):
    product, current_user, redirect = await _ensure_product_owner(request, product_id, db)
    if redirect is not None:
        return redirect

    if product.user_id != current_user.id and current_user.role not in {"admin", "superadmin"}:
        return RedirectResponse(url="/my-products", status_code=status.HTTP_303_SEE_OTHER)

    await db.execute(delete(CartItem).where(CartItem.product_id == product_id))
    await db.execute(delete(Favorite).where(Favorite.product_id == product_id))
    await db.execute(delete(OrderItem).where(OrderItem.product_id == product_id))
    await db.delete(product)
    await db.commit()

    redirect_target = "/catalog" if current_user.role in {"admin", "superadmin"} else "/my-products"
    return RedirectResponse(url=redirect_target, status_code=status.HTTP_303_SEE_OTHER)
