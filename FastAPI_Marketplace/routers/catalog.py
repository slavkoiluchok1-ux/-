from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from dependencies import get_current_user, get_current_user_or_redirect, get_optional_current_user
from models import (
    CartItem,
    Favorite,
    Order,
    OrderItem,
    Product,
    ProductMedia,
    Review,
    ReviewMedia,
    Tag,
    User,
    slugify,
)
from schemas import (
    ProductCreate,
    ProductMediaResponse,
    ProductResponse,
    ReviewCreate,
    ReviewMediaResponse,
    ReviewResponse,
    TagResponse,
)

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


def _parse_attributes(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    stripped = raw.strip()
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, dict):
            return parsed
        return None
    except (ValueError, TypeError):
        pairs = {}
        for line in stripped.splitlines():
            if "=" in line:
                k, v = line.split("=", 1)
                pairs[k.strip()] = v.strip()
            elif ":" in line:
                k, v = line.split(":", 1)
                pairs[k.strip()] = v.strip()
        return pairs or None


def _merge_product_attrs(
    base_attrs: dict[str, Any] | None,
    *,
    weight_dimensions: str | None = None,
    shipping_options: str | None = None,
    platform_server: str | None = None,
    rarity: str | None = None,
    execution_time: str | None = None,
) -> dict[str, Any] | None:
    merged: dict[str, Any] = {k: v for k, v in (base_attrs or {}).items()} if base_attrs else {}
    spec: dict[str, Any] = {}
    if weight_dimensions is not None:
        s = weight_dimensions.strip()
        if s:
            spec["weight_dimensions"] = s
    if shipping_options is not None:
        s = shipping_options.strip()
        if s:
            spec["shipping_options"] = s
    if platform_server is not None:
        s = platform_server.strip()
        if s:
            spec["platform_server"] = s
    if rarity is not None:
        s = rarity.strip()
        if s:
            spec["rarity"] = s
    if execution_time is not None:
        s = execution_time.strip()
        if s:
            spec["execution_time"] = s
    if spec:
        merged.update(spec)
    return merged or None


def _product_type_metadata(product: Product) -> dict[str, str]:
    attrs = product.attributes if isinstance(product.attributes, dict) else {}
    return {
        "weight_dimensions": (product.weight_dimensions or attrs.get("weight_dimensions") or "").strip(),
        "shipping_options": (product.shipping_options or attrs.get("shipping_options") or "").strip(),
        "platform_server": (product.platform_server or attrs.get("platform_server") or "").strip(),
        "rarity": (product.rarity or attrs.get("rarity") or "").strip(),
        "execution_time": (product.execution_time or attrs.get("execution_time") or "").strip(),
    }


async def _has_user_bought_product(db: AsyncSession, user_id: int, product_id: int) -> bool:
    if user_id <= 0:
        return False
    result = await db.execute(
        select(OrderItem.id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.user_id == user_id, OrderItem.product_id == product_id)
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _can_view_digital_content(db: AsyncSession, product: Product, current_user: User | None) -> bool:
    if current_user is None:
        return False
    if product.user_id == current_user.id:
        return True
    return await _has_user_bought_product(db, current_user.id, product.id)


async def _product_response_with_media(db: AsyncSession, product: Product, current_user: User | None = None) -> ProductResponse:
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
    tags = getattr(product, "tags", []) or []
    stock_status = _product_stock_status(product)
    metadata = _product_type_metadata(product)
    can_view_digital = await _can_view_digital_content(db, product, current_user)
    return ProductResponse(
        id=product.id,
        title=product.title,
        description=product.description,
        price=product.price,
        sale_price=product.sale_price,
        quantity=product.quantity,
        sku=product.sku,
        product_type=product.product_type.value if hasattr(product.product_type, "value") else product.product_type,
        is_draft=product.is_draft,
        attributes=product.attributes,
        digital_content=product.digital_content if can_view_digital else None,
        weight_dimensions=metadata["weight_dimensions"] or None,
        shipping_options=metadata["shipping_options"] or None,
        platform_server=metadata["platform_server"] or None,
        rarity=metadata["rarity"] or None,
        execution_time=metadata["execution_time"] or None,
        seller_phone=product.seller_phone,
        user_id=product.user_id,
        sales_count=product.sales_count,
        in_stock=stock_status["in_stock"],
        stock_status_label=stock_status["status_label"],
        created_at=product.created_at,
        updated_at=getattr(product, "updated_at", None),
        media=media,
        tags=[TagResponse(id=t.id, name=t.name, slug=t.slug) for t in tags],
    )


def _discount_percent(price: int | None, sale_price: float | None) -> int | None:
    if price and price > 0 and sale_price and sale_price > 0 and sale_price < price:
        return round(100 - (sale_price / price) * 100)
    return None


def _product_stock_status(product: Product) -> dict[str, Any]:
    quantity = int(getattr(product, "quantity", 0) or 0)
    in_stock = quantity > 0
    return {
        "quantity": quantity,
        "in_stock": in_stock,
        "status_label": "В наявності" if in_stock else "Немає в наявності",
        "status_class": "in-stock" if in_stock else "out-of-stock",
    }


def _tags_list(product: Product) -> list[dict[str, Any]]:
    tags = getattr(product, "tags", []) or []
    return [{"id": t.id, "name": t.name, "slug": t.slug} for t in tags]


def _tags_comma_str(product: Product) -> str:
    tags = _tags_list(product)
    return ", ".join(t["name"] for t in tags)


async def _fetch_or_create_tags(db: AsyncSession, raw_tags: str) -> list[Tag]:
    names = [n.strip() for n in (raw_tags or "").replace(";", ",").split(",") if n.strip()]
    names = list(dict.fromkeys(names))[:30]
    if not names:
        return []

    existing = (await db.execute(select(Tag).where(Tag.name.in_(names)))).scalars().all()
    existing_by_name = {t.name: t for t in existing}

    result: list[Tag] = []
    for name in names:
        if len(name) > 80:
            name = name[:80]
        if name in existing_by_name:
            result.append(existing_by_name[name])
            continue
        base_slug = slugify(name)
        slug = base_slug
        counter = 1
        while True:
            dup = (await db.execute(select(Tag).where(Tag.slug == slug))).scalar_one_or_none()
            if dup is None:
                break
            slug = f"{base_slug}-{counter}"
            counter += 1
        tag = Tag(name=name, slug=slug)
        db.add(tag)
        result.append(tag)
    await db.flush()
    return result


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    q: str | None = None,
    tag: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):

    stmt = select(Product).where(Product.is_draft == False)
    if type in {"physical", "digital", "game_item"}:
        stmt = stmt.where(Product.product_type == type)
    if tag:
        tag_obj = (await db.execute(
            select(Tag).where((Tag.slug == tag) | (Tag.name == tag))
        )).scalar_one_or_none()
        if tag_obj:
            stmt = stmt.where(Product.tags.any(Tag.id == tag_obj.id))
    if q and q.strip():
        term = q.strip().lower()
        stmt = stmt.where(
            (func.lower(Product.title).contains(term)) | (func.lower(Product.description).contains(term))
        )

    stmt = stmt.order_by(
        case((Product.quantity > 0, 0), else_=1),
        Product.sales_count.desc(),
        Product.created_at.desc(),
    )

    result = await db.execute(stmt)
    products = result.scalars().all()

    all_tags_rows = (await db.execute(select(Tag).order_by(Tag.name))).scalars().all()
    all_tags = [{"id": t.id, "name": t.name, "slug": t.slug} for t in all_tags_rows]

    catalog_products = []
    for product in products:
        media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
        first_image = media_rows[0].file_path if media_rows else None
        discount_pct = _discount_percent(product.price, product.sale_price)
        stock_status = _product_stock_status(product)
        catalog_products.append(
            {
                "id": product.id,
                "title": product.title,
                "description": product.description,
                "price": product.price,
                "sale_price": product.sale_price,
                "discount_percent": discount_pct,
                "quantity": product.quantity,
                "sku": product.sku,
                "product_type": product.product_type.value if hasattr(product.product_type, "value") else product.product_type,
                "is_draft": product.is_draft,
                "seller_phone": product.seller_phone,
                "image_url": first_image,
                "sales_count": product.sales_count,
                "created_at": product.created_at,
                "tags": _tags_list(product),
                "in_stock": stock_status["in_stock"],
                "stock_status_label": stock_status["status_label"],
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
            "active_tag": tag or "",
            "active_type": type or "",
            "all_tags": all_tags,
        },
    )


@router.get("/api/v1/search/autocomplete")
async def autocomplete_search(q: str | None = Query(default=None), db: AsyncSession = Depends(get_db)):
    term = (q or "").strip()
    if not term:
        return []

    stmt = (
        select(Product)
        .where(Product.is_draft == False)
        .where((func.lower(Product.title).contains(term.lower())) | (func.lower(Product.description).contains(term.lower())))
        .order_by(case((Product.quantity > 0, 0), else_=1), Product.sales_count.desc(), Product.created_at.desc())
        .limit(8)
    )
    result = await db.execute(stmt)
    products = result.scalars().all()

    payload = []
    for product in products:
        stock_status = _product_stock_status(product)
        payload.append(
            {
                "id": product.id,
                "title": product.title,
                "price": product.price,
                "product_type": product.product_type.value if hasattr(product.product_type, "value") else product.product_type,
                "in_stock": stock_status["in_stock"],
                "stock_status": stock_status["status_label"],
                "image_url": None,
            }
        )
    return payload


@router.get("/api/v1/products", response_model=list[ProductResponse])
async def list_products(
    q: str | None = Query(default=None),
    type: str | None = Query(default=None, alias="type"),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product).where(Product.is_draft == False)
    if type in {"physical", "digital", "game_item"}:
        stmt = stmt.where(Product.product_type == type)
    if q and q.strip():
        term = q.strip().lower()
        stmt = stmt.where((func.lower(Product.title).contains(term)) | (func.lower(Product.description).contains(term)))
    stmt = stmt.order_by(
        case((Product.quantity > 0, 0), else_=1),
        Product.sales_count.desc(),
        Product.created_at.desc(),
    )

    result = await db.execute(stmt)
    products = result.scalars().all()
    return [await _product_response_with_media(db, product) for product in products]


@router.get("/products/{product_id}", response_class=HTMLResponse)
@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail_page(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_current_user),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")

    seller = await db.get(User, product.user_id)
    media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
    reviews = (await db.execute(select(Review).where(Review.product_id == product.id).order_by(Review.created_at.desc()))).scalars().all()

    review_items = []
    total_rating = 0
    for review in reviews:
        review_media = (await db.execute(select(ReviewMedia).where(ReviewMedia.review_id == review.id))).scalars().all()
        review_user = await db.get(User, review.user_id)
        review_items.append({
            "id": review.id,
            "user_id": review.user_id,
            "rating": review.rating,
            "comment": review.comment,
            "created_at": review.created_at,
            "username": review_user.username if review_user else None,
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
    discount_pct = _discount_percent(product.price, product.sale_price)

    product_payload = await _serialize_product_detail(db, product, current_user)

    return templates.TemplateResponse(
        request,
        "product_detail.html",
        {
            "request": request,
            "current_user": current_user,
            "product": product_payload,
            "seller": seller,
            "reviews": review_items,
            "average_rating": average_rating,
            "reviews_count": len(reviews),
            "can_view_digital_content": product_payload["can_view_digital_content"],
        },
    )


@router.post("/api/v1/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    request: Request,
    title: str = Form(...),
    description: str = Form(...),
    price: int = Form(...),
    sale_price: float | None = Form(default=None),
    quantity: int = Form(...),
    sku: str | None = Form(default=None),
    product_type: str = Form(default="physical"),
    is_draft: bool = Form(default=False),
    tags_raw: str | None = Form(default=None),
    attributes_raw: str | None = Form(default=None),
    digital_content: str | None = Form(default=None),
    seller_phone: str | None = Form(default=None),
    weight_dimensions: str | None = Form(default=None),
    shipping_options: str | None = Form(default=None),
    platform_server: str | None = Form(default=None),
    rarity: str | None = Form(default=None),
    execution_time: str | None = Form(default=None),
    files: list[UploadFile] = File(default_factory=list),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not title.strip() or not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Назва та опис товару обов'язкові.")

    if product_type not in {"physical", "digital", "game_item"}:
        product_type = "physical"

    final_phone = (seller_phone or current_user.phone or "").strip() or None
    final_sku = (sku or "").strip() or None
    final_digital = (digital_content or "").strip() or None
    final_weight_dimensions = (weight_dimensions or "").strip() or None
    final_shipping_options = (shipping_options or "").strip() or None
    final_platform_server = (platform_server or "").strip() or None
    final_rarity = (rarity or "").strip() or None
    final_execution_time = (execution_time or "").strip() or None
    parsed_attrs = _parse_attributes(attributes_raw)
    merged_attrs = _merge_product_attrs(
        parsed_attrs,
        weight_dimensions=final_weight_dimensions,
        shipping_options=final_shipping_options,
        platform_server=final_platform_server,
        rarity=final_rarity,
        execution_time=final_execution_time,
    )

    if product_type == "digital" and not final_digital:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для цифрового товару обов'язково вкажіть цифровий ключ, посилання або текстовий вміст.")
    if product_type == "game_item" and not any([final_platform_server, final_rarity, final_execution_time]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для ігрового предмета обов'язково заповніть хоча б одне з полів: Сервер/Платформа, Рідкісність або Час виконання.")

    final_sale_price = None
    if sale_price is not None:
        try:
            sp = float(sale_price)
            if sp > 0:
                final_sale_price = sp
        except (TypeError, ValueError):
            final_sale_price = None

    product = Product(
        title=title.strip(),
        description=description.strip(),
        price=int(price),
        sale_price=final_sale_price,
        quantity=int(quantity),
        sku=final_sku,
        product_type=product_type,
        is_draft=bool(is_draft),
        attributes=merged_attrs,
        digital_content=final_digital,
        weight_dimensions=final_weight_dimensions,
        shipping_options=final_shipping_options,
        platform_server=final_platform_server,
        rarity=final_rarity,
        execution_time=final_execution_time,
        seller_phone=final_phone,
        user_id=current_user.id,
        sales_count=0,
    )
    db.add(product)
    await db.flush()

    product.tags = await _fetch_or_create_tags(db, tags_raw or "")

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


async def _serialize_product_detail(db: AsyncSession, product: Product, current_user: User | None = None) -> dict[str, Any]:
    media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
    seller = await db.get(User, product.user_id)
    metadata = _product_type_metadata(product)
    can_view_digital = await _can_view_digital_content(db, product, current_user)
    return {
        "id": product.id,
        "owner_id": product.user_id,
        "title": product.title,
        "description": product.description,
        "price": product.price,
        "sale_price": product.sale_price,
        "discount_percent": _discount_percent(product.price, product.sale_price),
        "quantity": product.quantity,
        "stock": product.stock,
        "sku": product.sku,
        "product_type": product.product_type.value if hasattr(product.product_type, "value") else product.product_type,
        "is_draft": product.is_draft,
        "attributes": product.attributes,
        "digital_content": product.digital_content if can_view_digital else None,
        "weight_dimensions": metadata["weight_dimensions"] or "",
        "shipping_options": metadata["shipping_options"] or "",
        "platform_server": metadata["platform_server"] or "",
        "rarity": metadata["rarity"] or "",
        "execution_time": metadata["execution_time"] or "",
        "seller_phone": product.seller_phone,
        "seller": seller,
        "media": [
            {"id": item.id, "file_path": item.file_path, "media_type": item.media_type}
            for item in media_rows
        ],
        "tags": _tags_list(product),
        "can_view_digital_content": can_view_digital,
    }


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
async def my_products_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    result: User | RedirectResponse = Depends(get_current_user_or_redirect),
):
    if isinstance(result, RedirectResponse):
        return result
    current_user = result

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
            "sale_price": product.sale_price,
            "quantity": product.quantity,
            "sku": product.sku,
            "product_type": product.product_type.value if hasattr(product.product_type, "value") else product.product_type,
            "is_draft": product.is_draft,
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


async def _ensure_product_owner(
    result: User | RedirectResponse,
    product_id: int,
    db: AsyncSession,
) -> tuple[Product | None, User | None, RedirectResponse | None]:
    if isinstance(result, RedirectResponse):
        return None, None, result
    current_user = result
    current_user.role = _user_role(current_user)

    product = await db.get(Product, product_id)
    if product is None:
        return None, current_user, RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)

    if product.user_id != current_user.id and current_user.role not in {"admin", "superadmin"}:
        return None, current_user, RedirectResponse(url="/my-products", status_code=status.HTTP_303_SEE_OTHER)

    return product, current_user, None


@router.get("/products/{product_id}/edit", response_class=HTMLResponse)
async def edit_product_page(
    request: Request,
    product_id: int,
    db: AsyncSession = Depends(get_db),
    result: User | RedirectResponse = Depends(get_current_user_or_redirect),
):
    product, current_user, redirect = await _ensure_product_owner(result, product_id, db)
    if redirect is not None:
        return redirect

    media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()

    attrs = product.attributes if isinstance(product.attributes, dict) else {}

    raw_lines = []
    for k, v in attrs.items():
        if k in {"weight_dimensions", "shipping_options", "platform_server", "rarity", "execution_time"}:
            continue
        raw_lines.append(f"{k}: {v}")
    attributes_text = "\n".join(raw_lines)

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
                "sale_price": product.sale_price,
                "quantity": product.quantity,
                "sku": product.sku or "",
                "product_type": product.product_type.value if hasattr(product.product_type, "value") else product.product_type,
                "is_draft": product.is_draft,
                "attributes_text": attributes_text,
                "digital_content": product.digital_content or "",
                "seller_phone": product.seller_phone or "",
                "weight_dimensions": attrs.get("weight_dimensions", "") or "",
                "shipping_options": attrs.get("shipping_options", "") or "",
                "platform_server": attrs.get("platform_server", "") or "",
                "rarity": attrs.get("rarity", "") or "",
                "execution_time": attrs.get("execution_time", "") or "",
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
    sale_price: float | None = Form(default=None),
    quantity: int = Form(...),
    sku: str | None = Form(default=None),
    product_type: str = Form(default="physical"),
    is_draft: bool = Form(default=False),
    attributes_raw: str | None = Form(default=None),
    digital_content: str | None = Form(default=None),
    seller_phone: str | None = Form(default=None),
    weight_dimensions: str | None = Form(default=None),
    shipping_options: str | None = Form(default=None),
    platform_server: str | None = Form(default=None),
    rarity: str | None = Form(default=None),
    execution_time: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    db: AsyncSession = Depends(get_db),
    result: User | RedirectResponse = Depends(get_current_user_or_redirect),
):
    product, current_user, redirect = await _ensure_product_owner(result, product_id, db)
    if redirect is not None:
        return redirect

    if not title.strip() or not description.strip():
        media_rows = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id))).scalars().all()
        attributes_text = attributes_raw or ""
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
                    "sale_price": sale_price,
                    "quantity": quantity,
                    "sku": sku or "",
                    "product_type": product_type,
                    "is_draft": is_draft,
                    "attributes_text": attributes_text,
                    "digital_content": digital_content or "",
                    "seller_phone": seller_phone or "",
                    "weight_dimensions": weight_dimensions or "",
                    "shipping_options": shipping_options or "",
                    "platform_server": platform_server or "",
                    "rarity": rarity or "",
                    "execution_time": execution_time or "",
                    "media": [
                        {"id": m.id, "file_path": m.file_path, "media_type": m.media_type}
                        for m in media_rows
                    ],
                },
                "error": "Назва та опис товару обов'язкові.",
            },
        )

    if product_type not in {"physical", "digital", "game_item"}:
        product_type = "physical"

    final_digital = (digital_content or "").strip() or None
    final_weight_dimensions = (weight_dimensions or "").strip() or None
    final_shipping_options = (shipping_options or "").strip() or None
    final_platform_server = (platform_server or "").strip() or None
    final_rarity = (rarity or "").strip() or None
    final_execution_time = (execution_time or "").strip() or None

    if product_type == "digital" and not final_digital:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для цифрового товару обов'язково вкажіть цифровий ключ, посилання або текстовий вміст.")
    if product_type == "game_item" and not any([final_platform_server, final_rarity, final_execution_time]):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Для ігрового предмета обов'язково заповніть хоча б одне з полів: Сервер/Платформа, Рідкісність або Час виконання.")

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

    final_sale_price = None
    if sale_price is not None:
        try:
            sp = float(sale_price)
            if sp > 0:
                final_sale_price = sp
        except (TypeError, ValueError):
            final_sale_price = None
    product.sale_price = final_sale_price

    product.sku = (sku or "").strip() or None
    product.product_type = product_type
    product.is_draft = bool(is_draft)

    parsed_attrs = _parse_attributes(attributes_raw)
    product.attributes = _merge_product_attrs(
        parsed_attrs,
        weight_dimensions=final_weight_dimensions,
        shipping_options=final_shipping_options,
        platform_server=final_platform_server,
        rarity=final_rarity,
        execution_time=final_execution_time,
    )
    product.digital_content = final_digital
    product.weight_dimensions = final_weight_dimensions
    product.shipping_options = final_shipping_options
    product.platform_server = final_platform_server
    product.rarity = final_rarity
    product.execution_time = final_execution_time
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
    result: User | RedirectResponse = Depends(get_current_user_or_redirect),
):
    product, current_user, redirect = await _ensure_product_owner(result, product_id, db)
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
