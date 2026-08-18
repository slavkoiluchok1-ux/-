from __future__ import annotations

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import CartItem, Order, OrderItem, Product, User
from schemas import CartItemCreate, CartItemOut, MessageResponse, OrderCreate, OrderOut, ProductListOut

router = APIRouter(tags=["cart"])
templates = Jinja2Templates(directory="Templates")


@router.get("/cart", response_class=HTMLResponse)
async def cart_page(request: Request, db: AsyncSession = Depends(get_db)):
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
        "cart.html",
        {"request": request, "current_user": current_user, "is_authenticated": current_user is not None},
    )


async def _serialize_cart_item(db: AsyncSession, item: CartItem) -> CartItemOut | None:
    product = await db.get(Product, item.product_id, options=[selectinload(Product.media)])
    if product is None:
        return None

    # Get first image from media if available
    image_url = None
    if product.media and len(product.media) > 0:
        image_url = product.media[0].file_path

    return CartItemOut(
        id=item.id,
        user_id=item.user_id,
        product_id=item.product_id,
        quantity=item.quantity,
        product=ProductListOut(
            id=product.id,
            title=product.title,
            description=product.description,
            price=product.price,
            quantity=product.quantity,
            seller_phone=product.seller_phone,
            user_id=product.user_id,
            sales_count=product.sales_count,
            created_at=product.created_at,
            media=[],
            image_url=image_url,
            average_rating=0.0,
        ),
    )


@router.get("/api/v1/cart", response_model=list[CartItemOut])
async def get_cart(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    items = (await db.execute(select(CartItem).where(CartItem.user_id == current_user.id).order_by(CartItem.id.desc()))).scalars().all()
    result: list[CartItemOut] = []
    for item in items:
        serialized = await _serialize_cart_item(db, item)
        if serialized is not None:
            result.append(serialized)
    return result


async def _parse_cart_item_create(request: Request) -> CartItemCreate:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірний формат даних кошика")
        product_id = payload.get("product_id")
        quantity = payload.get("quantity", 1)
        return CartItemCreate(product_id=int(product_id), quantity=max(1, int(quantity)))

    form = await request.form()
    product_id = form.get("product_id")
    quantity = form.get("quantity") or 1
    if product_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Відсутній product_id")
    return CartItemCreate(product_id=int(product_id), quantity=max(1, int(quantity)))


@router.post("/api/v1/cart/add", response_model=MessageResponse)
@router.post("/api/v1/cart", response_model=MessageResponse)
async def add_to_cart(request: Request, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    payload = await _parse_cart_item_create(request)

    product = await db.get(Product, payload.product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")

    item = await db.scalar(
        select(CartItem).where(CartItem.user_id == current_user.id, CartItem.product_id == payload.product_id)
    )
    if item is not None:
        item.quantity += payload.quantity
    else:
        db.add(CartItem(user_id=current_user.id, product_id=payload.product_id, quantity=payload.quantity))

    await db.commit()
    return MessageResponse(message="Товар додано до кошика")


@router.post("/cart/add")
async def add_to_cart_redirect(
    product_id: int = Form(...),
    quantity: int = Form(default=1),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар не знайдено")

    item = await db.scalar(
        select(CartItem).where(CartItem.user_id == current_user.id, CartItem.product_id == product_id)
    )
    if item is not None:
        item.quantity += quantity
    else:
        db.add(CartItem(user_id=current_user.id, product_id=product_id, quantity=quantity))

    await db.commit()
    return RedirectResponse(url="/cart", status_code=status.HTTP_303_SEE_OTHER)


async def _parse_cart_item_update(request: Request) -> tuple[int | None, int | None, int]:
    content_type = request.headers.get("content-type", "").lower()

    item_id: int | None = None
    product_id: int | None = None
    quantity: int = 0

    if "application/json" in content_type:
        payload = await request.json()
        if isinstance(payload, dict):
            raw_item_id = payload.get("item_id")
            raw_product_id = payload.get("product_id")
            raw_quantity = payload.get("quantity")

            if raw_item_id is not None:
                try:
                    item_id = int(raw_item_id)
                except (TypeError, ValueError):
                    item_id = None

            if raw_product_id is not None:
                try:
                    product_id = int(raw_product_id)
                except (TypeError, ValueError):
                    product_id = None

            if raw_quantity is not None:
                try:
                    quantity = int(raw_quantity)
                except (TypeError, ValueError):
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірне значення кількості")
    else:
        form = await request.form()
        raw_item_id = form.get("item_id")
        raw_product_id = form.get("product_id")
        raw_quantity = form.get("quantity")

        if raw_item_id is not None and str(raw_item_id).strip():
            try:
                item_id = int(str(raw_item_id).strip())
            except (TypeError, ValueError):
                item_id = None

        if raw_product_id is not None and str(raw_product_id).strip():
            try:
                product_id = int(str(raw_product_id).strip())
            except (TypeError, ValueError):
                product_id = None

        if raw_quantity is not None and str(raw_quantity).strip():
            try:
                quantity = int(str(raw_quantity).strip())
            except (TypeError, ValueError):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірне значення кількості")

    return item_id, product_id, quantity


@router.post("/api/v1/cart/update")
@router.patch("/api/v1/cart/update")
@router.patch("/api/v1/cart/{item_id}")
async def update_cart_item(
    request: Request,
    item_id: int | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    body_item_id, body_product_id, body_quantity = await _parse_cart_item_update(request)

    effective_item_id = item_id if item_id is not None else body_item_id
    effective_product_id = body_product_id
    effective_quantity = body_quantity

    target_item_id = effective_item_id

    if target_item_id is None and effective_product_id is not None:
        item = await db.scalar(
            select(CartItem).where(CartItem.user_id == current_user.id, CartItem.product_id == effective_product_id)
        )
        if not item:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар у кошику не знайдено")
        target_item_id = item.id

    if target_item_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Не вказано item_id або product_id")

    item = await db.get(CartItem, target_item_id)
    if not item or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар у кошику не знайдено")

    if effective_quantity <= 0:
        await db.delete(item)
    else:
        item.quantity = effective_quantity

    await db.commit()

    # Return updated cart data
    items = (await db.execute(select(CartItem).where(CartItem.user_id == current_user.id).order_by(CartItem.id.desc()))).scalars().all()
    result: list[CartItemOut] = []
    total = 0
    for cart_item in items:
        serialized = await _serialize_cart_item(db, cart_item)
        if serialized is not None:
            result.append(serialized)
            total += serialized.product.price * serialized.quantity

    return {
        "message": "Кількість оновлено",
        "items": result,
        "total": total
    }


@router.delete("/api/v1/cart/remove/{item_id}")
@router.delete("/api/v1/cart/{item_id}")
async def delete_cart_item(item_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    item = await db.get(CartItem, item_id)
    if not item or item.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Товар у кошику не знайдено")

    await db.delete(item)
    await db.commit()
    return {"message": "Товар видалено з кошика"}


async def _parse_order_create(request: Request) -> OrderCreate:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Невірний формат даних замовлення")
        return OrderCreate(**payload)

    form = await request.form()
    delivery_address = form.get("delivery_address", "").strip()
    phone = form.get("phone", "").strip()
    payment_method = form.get("payment_method", "Оплата при отриманні").strip() or "Оплата при отриманні"
    return OrderCreate(delivery_address=delivery_address, phone=phone, payment_method=payment_method)


@router.post("/api/v1/orders/checkout", response_model=OrderOut)
@router.post("/api/v1/orders", response_model=OrderOut)
async def checkout_order(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    order_data = await _parse_order_create(request)

    items = (await db.execute(select(CartItem).where(CartItem.user_id == current_user.id))).scalars().all()
    if not items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Кошик порожній")

    order = Order(
        user_id=current_user.id,
        total_price=0.0,
        status="created",
        delivery_address=order_data.delivery_address,
        payment_method=order_data.payment_method,
        phone=order_data.phone,
    )
    db.add(order)
    await db.flush()

    total = 0.0
    order_items: list[OrderItem] = []
    for cart_item in items:
        product = await db.get(Product, cart_item.product_id, options=[selectinload(Product.media)])
        if product is None:
            continue

        ordered_quantity = cart_item.quantity
        if product.quantity < ordered_quantity:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Недостатньо товару в наявності")

        product.quantity -= ordered_quantity
        product.sales_count += ordered_quantity
        total += float(product.price) * ordered_quantity

        order_items.append(
            OrderItem(
                order_id=order.id,
                product_id=product.id,
                quantity=ordered_quantity,
                price_at_purchase=float(product.price),
            )
        )

    if not order_items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Кошик порожній")

    order.total_price = total
    db.add_all(order_items)
    await db.execute(delete(CartItem).where(CartItem.user_id == current_user.id))
    await db.commit()
    await db.refresh(order)

    return OrderOut(
        id=order.id,
        user_id=order.user_id,
        total_price=order.total_price,
        status=order.status,
        delivery_address=order.delivery_address,
        payment_method=order.payment_method,
        phone=order.phone,
        created_at=order.created_at,
        items=[
            {
                "id": item.id,
                "order_id": item.order_id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price_at_purchase": item.price_at_purchase,
                "product_title": (await db.get(Product, item.product_id)).title if await db.get(Product, item.product_id) else None,
                "product_image": await _get_product_image_url(db, item.product_id),
            }
            for item in order_items
        ],
    )


async def _get_product_image_url(db: AsyncSession, product_id: int) -> str | None:
    product = await db.get(Product, product_id, options=[selectinload(Product.media)])
    if product and product.media and len(product.media) > 0:
        return product.media[0].file_path
    return None
