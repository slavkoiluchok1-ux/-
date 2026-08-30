from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from auth_utils import decode_access_token
from database import get_db
from dependencies import get_current_user
from models import Order, OrderItem, Product, ProductMedia, User
from schemas import OrderOut, SellerSalesAnalyticsOut, SellerSalesItemOut

router = APIRouter(tags=["orders"])
templates = Jinja2Templates(directory="Templates")


async def _get_product_image_url(db: AsyncSession, product_id: int) -> str | None:
    product = await db.get(Product, product_id, options=[selectinload(Product.media)])
    if product and product.media and len(product.media) > 0:
        return product.media[0].file_path
    return None


@router.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, db: AsyncSession = Depends(get_db)):
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
        "orders.html",
        {"request": request, "current_user": current_user, "is_authenticated": current_user is not None},
    )


@router.get("/api/v1/orders", response_model=list[OrderOut])
async def list_orders(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    orders = (
        await db.execute(select(Order).where(Order.user_id == current_user.id).order_by(Order.created_at.desc()))
    ).scalars().all()

    result: list[OrderOut] = []
    for order in orders:
        items = (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
        result.append(
            OrderOut(
                id=order.id,
                user_id=order.user_id,
                total_price=float(order.total_price),
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
                        "price_at_purchase": float(item.price_at_purchase),
                        "product_title": (await db.get(Product, item.product_id)).title if await db.get(Product, item.product_id) else None,
                        "product_image": await _get_product_image_url(db, item.product_id),
                    }
                    for item in items
                ],
            )
        )
    return result


@router.get("/api/v1/orders/{order_id}", response_model=OrderOut)
async def get_order_detail(order_id: int, current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    order = await db.get(Order, order_id)
    if not order or order.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Замовлення не знайдено")

    items = (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
    return OrderOut(
        id=order.id,
        user_id=order.user_id,
        total_price=float(order.total_price),
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
                "price_at_purchase": float(item.price_at_purchase),
                "product_title": (await db.get(Product, item.product_id)).title if await db.get(Product, item.product_id) else None,
                "product_image": await _get_product_image_url(db, item.product_id),
            }
            for item in items
        ],
    )


@router.get("/api/v1/seller/sales", response_model=SellerSalesAnalyticsOut)
async def get_seller_sales(
    q: str | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(OrderItem, Order, Product)
        .join(Order, Order.id == OrderItem.order_id)
        .join(Product, Product.id == OrderItem.product_id)
        .where(Product.user_id == current_user.id)
        .where(Order.status != "cancelled")
    )

    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(
            or_(
                Product.title.ilike(term),
                cast(Order.id, String).ilike(term),
            )
        )

    stmt = stmt.order_by(Order.created_at.desc(), OrderItem.id.desc())
    rows = (await db.execute(stmt)).all()

    items: list[SellerSalesItemOut] = []
    total_profit = 0.0
    sold_count = 0

    for order_item, order, product in rows:
        product_media = (await db.execute(select(ProductMedia).where(ProductMedia.product_id == product.id).limit(1))).scalars().first()
        price_per_item = float(order_item.price_at_purchase or product.price)
        quantity = int(order_item.quantity or 0)
        total_amount = price_per_item * quantity

        total_profit += total_amount
        sold_count += quantity

        items.append(
            SellerSalesItemOut(
                order_id=order.id,
                product_id=product.id,
                title=product.title,
                image_url=product_media.file_path if product_media else None,
                quantity=quantity,
                price_per_item=price_per_item,
                total_amount=total_amount,
                sold_at=order.created_at,
            )
        )

    return SellerSalesAnalyticsOut(
        total_profit=total_profit,
        sold_count=sold_count,
        items=items,
    )
