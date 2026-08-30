from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

from enum import Enum

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import case, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot import ensure_user_tg_link_code
from database import get_db
from dependencies import get_current_user
from models import CartItem, Category, Favorite, OrderItem, Product, ProductMedia, ProductType, Review, ReviewMedia, User
from schemas import ProductCreate, ProductMediaResponse, ProductResponse, ReviewCreate, ReviewMediaResponse, ReviewResponse

router = APIRouter(tags=["catalog"])

templates = Jinja2Templates(directory="Templates")
MAX_UPLOAD_SIZE_BYTES = 1_073_741_824
MAX_SQLITE_INT = 2_147_483_647
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


def _coerce_product_type(value: str | None) -> str:
    if not value:
        return ProductType.PHYSICAL.value
    aliases = {
        "game": ProductType.GAME_ITEM.value,
        "ігри": ProductType.GAME_ITEM.value,
        "акаунти": ProductType.GAME_ITEM.value,
        "аккаунти": ProductType.GAME_ITEM.value,
        "софт": ProductType.DIGITAL.value,
        "курси": ProductType.DIGITAL.value,
        "цифрові товари": ProductType.DIGITAL.value,
        "фізичний": ProductType.PHYSICAL.value,
    }
    normalized = str(value).strip().lower()
    if normalized in aliases:
        return aliases[normalized]
    allowed = {item.value for item in ProductType}
    if normalized in allowed:
        return normalized
    return ProductType.PHYSICAL.value


DEFAULT_CATEGORY_TREE: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("auto", "Автотовари", [
        ("auto_parts", "Запчастини", "physical"),
        ("auto_chem", "Автохімія", "physical"),
        ("auto_interior", "Салон", "physical"),
    ]),
    ("home_garden", "Дім та сад", [
        ("furniture", "Меблі", "physical"),
        ("home_decor", "Декор", "physical"),
        ("tools", "Інструменти", "physical"),
        ("tableware", "Посуд", "physical"),
    ]),
    ("electronics", "Електроніка", [
        ("smartphones", "Смартфони", "physical"),
        ("laptops", "Ноутбуки", "physical"),
        ("components", "Комплектуючі", "physical"),
        ("accessories", "Аксесуари", "physical"),
    ]),
    ("beauty_health", "Краса та здоров'я", [
        ("cosmetics", "Косметика", "physical"),
        ("perfumery", "Парфумерія", "physical"),
        ("care", "Догляд", "physical"),
    ]),
    ("craft", "Крафт та Хендмейд", [
        ("jewelry", "Прикраси", "physical"),
        ("handmade_decor", "Декор ручної роботи", "physical"),
    ]),
    ("clothing", "Одяг та взуття", [
        ("mens", "Чоловічий", "physical"),
        ("womens", "Жіночий", "physical"),
        ("kids_clothes", "Дитячий", "physical"),
        ("shoes", "Взуття", "physical"),
    ]),
    ("sports", "Спорт та відпочинок", [
        ("fitness", "Тренажери", "physical"),
        ("tourism", "Туризм", "physical"),
        ("bicycles", "Велосипеди", "physical"),
    ]),
    ("digital_goods", "Цифрові товари", [
        ("games", "Ігри", "game_item"),
        ("software", "Софт", "digital"),
        ("accounts", "Акаунти", "game_item"),
        ("courses", "Курси", "digital"),
    ]),
]

CATEGORY_ALIASES: dict[str, list[str]] = {
    "auto": ["auto", "avtotovary", "автотовари"],
    "auto_parts": ["auto_parts", "zapchastyny", "запчастини"],
    "auto_chem": ["auto_chem", "avtokhimiya", "автохімія"],
    "auto_interior": ["auto_interior", "salon", "салон"],
    "home_garden": ["home_garden", "dim-ta-sad", "дім та сад"],
    "furniture": ["furniture", "mebli", "меблі"],
    "home_decor": ["home_decor", "dekor", "декор"],
    "tools": ["tools", "instrumenty", "інструменти"],
    "tableware": ["tableware", "posud", "посуд"],
    "electronics": ["electronics", "elektronika", "електроніка"],
    "smartphones": ["smartphones", "smartfony", "смартфони"],
    "laptops": ["laptops", "noutbuki", "ноутбуки"],
    "components": ["components", "komplektuyuchi", "комплектуючі"],
    "accessories": ["accessories", "aksesuary", "аксесуари"],
    "beauty_health": ["beauty_health", "krasa-ta-zdorovya", "краса та здоров'я"],
    "cosmetics": ["cosmetics", "kosmetyka", "косметика"],
    "perfumery": ["perfumery", "parfumeriya", "парфумерія"],
    "care": ["care", "dohlyad", "догляд"],
    "craft": ["craft", "kraft-ta-hendmeyd", "крафт та хендмейд"],
    "jewelry": ["jewelry", "prykrasy", "прикраси"],
    "handmade_decor": ["handmade_decor", "dekor-ruchnoyi-roboty", "декор ручної роботи"],
    "clothing": ["clothing", "odyag-ta-vzuttya", "одяг та взуття"],
    "mens": ["mens", "cholovichiy", "чоловічий"],
    "womens": ["womens", "zhinochiy", "жіночий"],
    "kids_clothes": ["kids_clothes", "dityachiy", "дитячий"],
    "shoes": ["shoes", "vzuttia", "взуття"],
    "sports": ["sports", "sport-ta-vidpochynok", "спорт та відпочинок"],
    "fitness": ["fitness", "trenazhery", "тренажери"],
    "tourism": ["tourism", "turystychni-tovary", "туризм"],
    "bicycles": ["bicycles", "velosyped", "велосипеди"],
    "digital_goods": ["digital_goods", "tsyfrovi-tovary", "цифрові товари"],
    "games": ["games", "igry", "ігри"],
    "software": ["software", "soft", "софт"],
    "accounts": ["accounts", "rahunky", "акаунти"],
    "courses": ["courses", "kursy", "курси"],
}


async def ensure_default_categories(db: AsyncSession) -> dict[str, int]:
    slug_to_id: dict[str, int] = {}
    existing_rows = (await db.execute(select(Category))).scalars().all()
    by_slug = {c.slug: c for c in existing_rows if getattr(c, "slug", None)}
    by_name = {c.name.strip().lower(): c for c in existing_rows if getattr(c, "name", None)}

    for parent_slug, parent_name, children in DEFAULT_CATEGORY_TREE:
        parent = by_slug.get(parent_slug) or by_name.get(parent_name.lower())
        if parent is None:
            parent = Category(
                name=parent_name,
                slug=parent_slug,
                icon=None,
                parent_id=None,
            )
            db.add(parent)
            await db.flush()
        else:
            if parent.name != parent_name:
                parent.name = parent_name
            if parent.parent_id is not None:
                parent.parent_id = None
        slug_to_id[parent_slug] = parent.id

        for child_slug, child_name, _ in children:
            child = by_slug.get(child_slug) or by_name.get(child_name.lower())
            if child is None:
                child = Category(
                    name=child_name,
                    slug=child_slug,
                    icon=None,
                    parent_id=parent.id,
                )
                db.add(child)
                await db.flush()
            else:
                if child.name != child_name:
                    child.name = child_name
                if child.parent_id != parent.id:
                    child.parent_id = parent.id
            slug_to_id[child_slug] = child.id

    await db.commit()
    return slug_to_id


async def resolve_category_id(
    db: AsyncSession,
    category_id_form_value: int | str | None = None,
    category_slug_form_value: str | None = None,
    category: str | int | None = None,
    category_id: int | str | None = None,
    category_slug: str | None = None,
) -> int | None:
    candidates = [category, category_slug, category_id, category_slug_form_value, category_id_form_value]
    raw_value: str | None = None
    for cand in candidates:
        if cand not in (None, ""):
            cand_str = str(cand).strip()
            if cand_str:
                raw_value = cand_str
                break

    if raw_value is None or raw_value == "":
        return None

    if raw_value.isdigit():
        numeric_id = int(raw_value)
        check = await db.get(Category, numeric_id)
        if check is not None:
            return numeric_id

    normalized = raw_value.lower()
    categories = (await db.execute(select(Category))).scalars().all()
    for cat in categories:
        if cat.slug and cat.slug.lower() == normalized:
            return int(cat.id)
        if cat.name and cat.name.strip().lower() == normalized:
            return int(cat.id)

    alias_matches: set[str] = set()
    for key, aliases in CATEGORY_ALIASES.items():
        if normalized == key.lower() or normalized in [a.lower() for a in aliases]:
            alias_matches.add(key.lower())
            for a in aliases:
                alias_matches.add(a.lower())

    if alias_matches:
        for cat in categories:
            if (cat.slug and cat.slug.lower() in alias_matches) or (cat.name and cat.name.strip().lower() in alias_matches):
                return int(cat.id)

    await ensure_default_categories(db)
    categories = (await db.execute(select(Category))).scalars().all()
    for cat in categories:
        if cat.slug and cat.slug.lower() == normalized:
            return int(cat.id)
        if cat.name and cat.name.strip().lower() == normalized:
            return int(cat.id)
        if alias_matches and ((cat.slug and cat.slug.lower() in alias_matches) or (cat.name and cat.name.strip().lower() in alias_matches)):
            return int(cat.id)

    for cat in categories:
        if cat.name and normalized in cat.name.lower():
            return int(cat.id)

    return None


def _parse_tags(value: str | None) -> list[str]:
    if value is None:
        return []
    tags = [part.strip() for part in str(value).replace(";", ",").split(",")]
    return [tag for tag in tags if tag]


def _parse_attributes(value: str | None) -> dict[str, str]:
    if value is None:
        return {}
    raw = str(value).strip()
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict):
            return {str(key): str(val) for key, val in payload.items() if str(key).strip()}
    except json.JSONDecodeError:
        pass

    result: dict[str, str] = {}
    for piece in raw.split(";"):
        if ":" not in piece:
            continue
        key, val = piece.split(":", 1)
        key = key.strip()
        val = val.strip()
        if key:
            result[key] = val
    return result


def _serialize_product_response(product: Product, media: list[ProductMediaResponse], current_user: User | None = None) -> ProductResponse:
    allow_digital_content = bool(
        product.digital_content
        and (
            current_user is not None and (product.user_id == current_user.id or current_user.is_admin or current_user.is_superuser)
        )
    )
    return ProductResponse(
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
        category_id=product.category_id,
        sales_count=product.sales_count,
        product_type=ProductType(product.product_type or ProductType.PHYSICAL.value),
        sku=product.sku,
        sale_price=product.sale_price,
        is_draft=bool(product.is_draft),
        tags=_parse_tags(product.tags),
        attributes=_parse_attributes(product.attributes),
        digital_content=product.digital_content if allow_digital_content else None,
        created_at=product.created_at,
        media=media,
    )


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
    return _serialize_product_response(product, media, current_user=current_user)


@router.get("/catalog", response_class=HTMLResponse)
async def catalog_page(
    request: Request,
    q: str | None = None,
    category: str | None = None,
    category_id: int | None = None,
    sort: str | None = None,
    db: AsyncSession = Depends(get_db),
):
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

    selected_category = None
    if category_id is not None:
        selected_category = await db.get(Category, category_id)
    elif category and category.strip():
        slug = category.strip().lower()
        selected_category = await db.scalar(select(Category).where(Category.slug == slug))

    stmt = select(Product).outerjoin(Category, Product.category_id == Category.id).where(Product.is_draft.is_(False)).distinct()

    if selected_category is not None:
        category_ids = await _resolve_category_ids(db, category_id=selected_category.id, category_slug=None)
        if category_ids:
            stmt = stmt.where(Product.category_id.in_(sorted(category_ids)))

    if q and q.strip():
        term = q.strip()
        pattern = f"%{term}%"
        stmt = stmt.where(
            (Product.title.ilike(pattern))
            | (Product.description.ilike(pattern))
            | (Category.name.ilike(pattern))
        )

    sort_value = (sort or "popular").strip().lower()
    in_stock_expr = (Product.quantity > 0).desc()
    if sort_value == "newest":
        stmt = stmt.order_by(in_stock_expr, Product.created_at.desc(), Product.sales_count.desc(), Product.id.desc())
    elif sort_value == "price_asc":
        stmt = stmt.order_by(in_stock_expr, Product.price.asc(), Product.sales_count.desc(), Product.id.desc())
    elif sort_value == "price_desc":
        stmt = stmt.order_by(in_stock_expr, Product.price.desc(), Product.sales_count.desc(), Product.id.desc())
    else:
        stmt = stmt.order_by(in_stock_expr, Product.sales_count.desc(), Product.created_at.desc(), Product.id.desc())

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
                "stock": product.quantity,
                "in_stock": product.quantity > 0,
                "is_available": product.quantity > 0,
                "seller_phone": product.seller_phone,
                "image_url": first_image,
                "sales_count": product.sales_count,
                "created_at": product.created_at,
            }
        )

    category_rows = (
        await db.execute(
            select(Category)
            .where(Category.parent_id.is_(None))
            .options(selectinload(Category.children))
            .order_by(Category.name.asc())
        )
    ).scalars().all()

    return templates.TemplateResponse(
        request,
        "catalog.html",
        {
            "request": request,
            "current_user": current_user,
            "products": catalog_products,
            "q": q or "",
            "categories": category_rows,
            "selected_category": selected_category,
            "selected_sort": sort_value,
            "selected_category_slug": (category or "").strip(),
        },
    )


async def _resolve_category_ids(
    db: AsyncSession,
    category_id: int | None = None,
    category_slug: str | None = None,
) -> set[int]:
    if category_id is None and not category_slug:
        return set()

    categories = (await db.execute(select(Category).options(selectinload(Category.children)))).scalars().all()
    category_map = {item.id: item for item in categories}
    target = None

    if category_id is not None:
        target = category_map.get(category_id)
    elif category_slug:
        target = next((item for item in categories if item.slug == category_slug.strip().lower()), None)

    if target is None:
        return set()

    matched: set[int] = set()

    def walk(node: Category) -> None:
        matched.add(node.id)
        for child in node.children:
            walk(child)

    walk(target)
    return matched


@router.get("/api/v1/search/autocomplete")
async def autocomplete_search(
    q: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    term = (q or "").strip()
    if not term:
        return {"q": "", "products": [], "categories": []}

    search_pattern = f"%{term}%"

    product_rows = (
        await db.execute(
            select(Product.id, Product.title, Product.price, Product.quantity, Product.sales_count)
            .where(Product.title.ilike(search_pattern))
            .order_by((Product.quantity > 0).desc(), Product.sales_count.desc(), Product.title.asc())
            .limit(5)
        )
    ).all()

    category_rows = (
        await db.execute(
            select(Category.id, Category.name, Category.slug)
            .where(Category.name.ilike(search_pattern))
            .order_by(Category.name.asc())
            .limit(3)
        )
    ).all()

    return {
        "q": term,
        "products": [
            {
                "id": product_id,
                "title": title,
                "price": price,
                "quantity": quantity,
                "stock": quantity,
                "in_stock": bool(quantity and quantity > 0),
                "is_available": bool(quantity and quantity > 0),
            }
            for product_id, title, price, quantity, _sales_count in product_rows
        ],
        "categories": [{"id": category_id, "name": name, "slug": slug} for category_id, name, slug in category_rows],
    }


@router.get("/api/v1/products", response_model=list[ProductResponse])
async def list_products(
    q: str | None = Query(default=None),
    category_id: int | None = Query(default=None),
    category_slug: str | None = Query(default=None),
    sort: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Product)
        .outerjoin(Category, Product.category_id == Category.id)
        .where(Product.is_draft.is_(False))
        .distinct()
    )

    category_ids = await _resolve_category_ids(db, category_id, category_slug)
    if category_ids:
        stmt = stmt.where(Product.category_id.in_(sorted(category_ids)))

    if q and q.strip():
        term = q.strip()
        pattern = f"%{term}%"
        stmt = stmt.where(
            (Product.title.ilike(pattern))
            | (Product.description.ilike(pattern))
            | (Category.name.ilike(pattern))
        )

    sort_value = (sort or "popular").strip().lower()
    in_stock_expr = (Product.quantity > 0).desc()
    if sort_value == "newest":
        stmt = stmt.order_by(in_stock_expr, Product.created_at.desc(), Product.sales_count.desc(), Product.id.desc())
    elif sort_value == "price_asc":
        stmt = stmt.order_by(in_stock_expr, Product.price.asc(), Product.sales_count.desc(), Product.id.desc())
    elif sort_value == "price_desc":
        stmt = stmt.order_by(in_stock_expr, Product.price.desc(), Product.sales_count.desc(), Product.id.desc())
    else:
        stmt = stmt.order_by(in_stock_expr, Product.sales_count.desc(), Product.created_at.desc(), Product.id.desc())

    result = await db.execute(stmt)
    products = result.scalars().all()
    return [await _product_response_with_media(db, product) for product in products]


@router.get("/products/{product_id}", response_class=HTMLResponse)
@router.get("/product/{product_id}", response_class=HTMLResponse)
async def product_detail_page(request: Request, product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")
    if product.is_draft:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Чернетка товару недоступна для перегляду")

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

    is_owner = bool(current_user and product.user_id == current_user.id)
    is_admin = bool(current_user and (current_user.is_admin or current_user.is_superuser))
    digital_content = product.digital_content if (product.product_type in {ProductType.DIGITAL.value, ProductType.GAME.value} and (is_owner or is_admin)) else None

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
                "stock": product.quantity,
                "in_stock": product.quantity > 0,
                "is_available": product.quantity > 0,
                "seller_phone": product.seller_phone,
                "seller": seller,
                "product_type": product.product_type,
                "sku": product.sku,
                "sale_price": product.sale_price,
                "tags": _parse_tags(product.tags),
                "attributes": _parse_attributes(product.attributes),
                "digital_content": digital_content,
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
    price: int = Form(..., ge=0, le=MAX_SQLITE_INT),
    quantity: int = Form(..., ge=0, le=MAX_SQLITE_INT),
    seller_phone: str | None = Form(default=None),
    category: str | None = Form(default=None),
    category_id: str | None = Form(default=None),
    category_slug: str | None = Form(default=None),
    product_type: str = Form(default=ProductType.PHYSICAL.value),
    sku: str | None = Form(default=None),
    sale_price: int | None = Form(default=None),
    is_draft: bool = Form(default=False),
    tags: str | None = Form(default=None),
    attributes: str | None = Form(default=None),
    digital_content: str | None = Form(default=None),
    files: list[UploadFile] = File(default_factory=list),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if not title.strip() or not description.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Назва та опис товару обов'язкові.")

    final_category_id = await resolve_category_id(db, category_id=category_id, category_slug=category_slug, category=category)
    if (category is not None or category_id is not None or category_slug is not None) and final_category_id is None:
        cat_val = category or category_slug or category_id
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Категорію '{cat_val}' не знайдено")

    type_value = _coerce_product_type(product_type)
    if type_value in {ProductType.DIGITAL.value, ProductType.GAME.value, ProductType.GAME_ITEM.value} and not digital_content and quantity > 0:
        digital_content = ""

    final_price = int(price)
    final_quantity = int(quantity)
    if final_price < 0 or final_quantity < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ціна та кількість не можуть бути від'ємними.")
    if final_price > MAX_SQLITE_INT or final_quantity > MAX_SQLITE_INT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ціна або кількість перевищують допустимий ліміт.")

    sale_price_value = int(sale_price) if sale_price is not None else None
    if sale_price_value is not None and sale_price_value < 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Знижена ціна не може бути від'ємною.")

    final_phone = (seller_phone or current_user.phone or "").strip() or None
    sku_value = (sku or "").strip() or None
    tags_value = ", ".join(_parse_tags(tags))
    attributes_value = json.dumps(_parse_attributes(attributes), ensure_ascii=False) if attributes else None
    digital_content_value = (digital_content or "").strip() or None

    product = Product(
        title=title.strip(),
        description=description.strip(),
        price=final_price,
        quantity=final_quantity,
        seller_phone=final_phone,
        user_id=current_user.id,
        category_id=final_category_id,
        product_type=type_value,
        sku=sku_value,
        sale_price=sale_price_value,
        is_draft=bool(is_draft),
        tags=tags_value or None,
        attributes=attributes_value,
        digital_content=digital_content_value,
        sales_count=0,
    )
    db.add(product)
    await db.flush()

    for uploaded_file in files:
        if uploaded_file is None or not getattr(uploaded_file, "filename", None):
            continue
        if not uploaded_file.filename.strip():
            continue
        file_path, media_type = await _save_uploaded_media(uploaded_file)
        db.add(ProductMedia(product_id=product.id, file_path=file_path, media_type=media_type))

    await db.commit()
    await db.refresh(product)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return await _product_response_with_media(db, product, current_user=current_user)

    if request.headers.get("accept", "").lower().startswith("application/json"):
        return await _product_response_with_media(db, product, current_user=current_user)

    return RedirectResponse(url="/catalog", status_code=status.HTTP_303_SEE_OTHER)


@router.delete("/api/v1/products/media/{media_id}")
async def delete_product_media(
    media_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    media = await db.get(ProductMedia, media_id)
    if media is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Фото не знайдено")

    product = await db.get(Product, media.product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")

    is_owner = product.user_id == current_user.id
    is_admin = bool(current_user.is_admin or current_user.is_superuser)
    if not (is_owner or is_admin):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Немає доступу для видалення фото")

    file_path = media.file_path
    if isinstance(file_path, str) and file_path.startswith("/"):
        relative_path = file_path.lstrip("/")
        disk_path = Path(__file__).resolve().parents[1] / relative_path
        if disk_path.exists() and disk_path.is_file():
            try:
                os.remove(disk_path)
            except OSError:
                pass

    await db.delete(media)
    await db.commit()
    return {"status": "success", "message": "Фото видалено"}


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
        auth_header = request.headers.get("Authorization") or request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token_value = auth_header.replace("Bearer ", "").strip()
        elif auth_header:
            token_value = auth_header.strip()

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

    await ensure_user_tg_link_code(current_user, db)

    stmt = (
        select(Product)
        .where(Product.user_id == current_user.id)
        .options(selectinload(Product.category))
        .order_by((Product.quantity > 0).desc(), Product.sales_count.desc(), Product.created_at.desc(), Product.id.desc())
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
            "stock": product.quantity,
            "in_stock": product.quantity > 0,
            "is_available": product.quantity > 0,
            "seller_phone": product.seller_phone,
            "category": product.category,
            "product_type": product.product_type,
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
            "telegram_bot_link": "https://t.me/FastMoneyMarketBot",
        },
    )


async def _ensure_product_owner(request: Request, product_id: int, db: AsyncSession) -> tuple[Product | None, User | None, RedirectResponse | None]:
    current_user = await _get_current_user_from_request(request, db)
    if current_user is None:
        return None, None, RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

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
    category_slug = ""
    if getattr(product, "category_id", None) is not None:
        category_row = await db.get(Category, product.category_id)
        category_slug = getattr(category_row, "slug", "") or ""

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
                "product_type": product.product_type,
                "category_slug": category_slug,
                "sku": product.sku,
                "sale_price": product.sale_price,
                "tags": product.tags or "",
                "attributes": product.attributes or "",
                "digital_content": product.digital_content or "",
                "is_draft": bool(product.is_draft),
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
    category: str | None = Form(default=None),
    category_slug: str | None = Form(default=None),
    category_id: str | None = Form(default=None),
    product_type: str = Form(default=ProductType.PHYSICAL.value),
    sku: str | None = Form(default=None),
    sale_price: int | None = Form(default=None),
    is_draft: bool = Form(default=False),
    tags: str | None = Form(default=None),
    attributes: str | None = Form(default=None),
    digital_content: str | None = Form(default=None),
    file: UploadFile | None = File(default=None),
    files: list[UploadFile] = File(default_factory=list),
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
                    "product_type": product_type,
                    "category_slug": category or category_slug or "",
                    "sku": sku,
                    "sale_price": sale_price,
                    "tags": tags or "",
                    "attributes": attributes or "",
                    "digital_content": digital_content or "",
                    "is_draft": bool(is_draft),
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
        product.price = max(0, int(price))
    except (TypeError, ValueError):
        product.price = 0
    try:
        product.quantity = max(0, int(quantity))
    except (TypeError, ValueError):
        product.quantity = 0
    product.seller_phone = (seller_phone or current_user.phone or "").strip() or None
    product.product_type = _coerce_product_type(product_type)
    product.sku = (sku or "").strip() or None
    product.sale_price = int(sale_price) if sale_price is not None and sale_price >= 0 else None
    product.is_draft = bool(is_draft)
    product.tags = ", ".join(_parse_tags(tags)) or None
    product.attributes = json.dumps(_parse_attributes(attributes), ensure_ascii=False) if attributes else None
    product.digital_content = (digital_content or "").strip() or None

    final_category_id = await resolve_category_id(db, category_id=category_id, category_slug=category_slug, category=category)
    if final_category_id is not None:
        product.category_id = final_category_id

    all_files = []
    if file is not None and getattr(file, "filename", None) and file.filename.strip():
        all_files.append(file)
    for f in files:
        if f is not None and getattr(f, "filename", None) and f.filename.strip():
            all_files.append(f)

    for upload in all_files:
        file_path, media_type = await _save_uploaded_media(upload)
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
