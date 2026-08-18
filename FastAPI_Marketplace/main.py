from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import httpx
import jwt
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database import Base, DatabaseUnavailableError, async_session, cleanup_html_redirect_product, engine, ensure_schema, get_db
from dependencies import get_current_admin_user, get_current_superuser, get_current_user
from models import CartItem, Complaint, Favorite, Order, OrderItem, Product, Review, Resume, User
from routers.auth import router as auth_router
from routers.cart import router as cart_router
from routers.catalog import router as catalog_router
from routers.complaints import router as complaints_router
from routers.favorites import router as favorites_router
from routers.orders import router as orders_router
from routers.profile import router as profile_router
from routers.resume import router as resume_router
from routers.admin import router as admin_router
from schemas import (
    CartItemCreate,
    CartItemOut,
    ComplaintCreate,
    ComplaintOut,
    FavoriteOut,
    MessageResponse,
    OrderOut,
    OrderStatusUpdate,
    ProductCreate,
    ProductDetailOut,
    ProductOut,
    ResumeCreate,
    ResumeOut,
    ReviewCreate,
    ReviewOut,
    StatsOut,
    Token,
    UploadResponse,
    UserCreate,
    UserLogin,
    UserPublic,
)


logger = logging.getLogger(__name__)

APP_BRAND = "Fast Money"
DB_UNAVAILABLE_MESSAGE = "База даних тимчасово недоступна. Перевірте запуск PostgreSQL на 127.0.0.1:5432"

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
PHOTO_DIR = UPLOAD_DIR / "photos"
VIDEO_DIR = UPLOAD_DIR / "videos"
STATIC_DIR = BASE_DIR / "static"
IMAGES_DIR = BASE_DIR / "images"

for directory in (UPLOAD_DIR, PHOTO_DIR, VIDEO_DIR, STATIC_DIR, IMAGES_DIR):
    directory.mkdir(parents=True, exist_ok=True)

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-marketplace-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "mock_token")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "mock_id")
SUPERADMIN_EMAIL = "superadmin@scootershop.com"
SUPERADMIN_PASSWORD = "admin12345"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer(auto_error=False)

templates = Jinja2Templates(directory=str(BASE_DIR / "Templates"))


async def create_db_tables():
    await ensure_schema()


async def ensure_superadmin():
    async with async_session() as session:
        existing = await session.scalar(
            select(User).where((User.username == "superadmin") | (User.email == "superadmin"))
        )
        if existing:
            if not existing.is_superuser:
                existing.is_superuser = True
                existing.is_admin = True
                await session.commit()
            return

        user = User(
            username="superadmin",
            email="superadmin",
            display_name="Super Admin",
            is_active=True,
            is_admin=True,
            is_superuser=True,
        )
        user.set_password("12345")
        session.add(user)
        await session.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        await create_db_tables()
        await cleanup_html_redirect_product()
        await ensure_superadmin()
    except Exception as exc:
        logger.warning(
            "Помилка підключення до БД. Перевірте налаштування .env та запуск PostgreSQL. Деталі: %s",
            exc,
        )
    yield

app = FastAPI(
    title=APP_BRAND,
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(favorites_router)
app.include_router(complaints_router)
app.include_router(resume_router)
app.include_router(profile_router)
app.include_router(admin_router)


@app.exception_handler(DatabaseUnavailableError)
async def database_unavailable_exception_handler(request: Request, exc: DatabaseUnavailableError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": DB_UNAVAILABLE_MESSAGE},
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")
templates = Jinja2Templates(directory=str(BASE_DIR / "Templates"))


async def get_template_user(request: Request, db: AsyncSession) -> User | None:
    token = request.cookies.get("access_token")
    if not token:
        return None

    clean_token = token.replace("Bearer ", "").strip()
    try:
        payload = decode_access_token(clean_token)
        user_id = payload.get("sub")
        if user_id is None:
            return None
        return await db.get(User, int(user_id))
    except HTTPException:
        return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_template_user(request, db)
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "current_user": current_user, "is_authenticated": current_user is not None},
    )


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_template_user(request, db)
    return templates.TemplateResponse(request, "login.html", {"request": request, "current_user": current_user})


@app.post("/login")
async def login_page_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    identifier = email.strip()
    user = await db.scalar(
        select(User).where(or_(User.email == identifier.lower(), User.username == identifier))
    )
    error = None
    if user is None or not user.verify_password(password):
        error = "Невірний логін або пароль"
    elif not user.is_active:
        error = "Обліковий запис деактивовано"

    if error:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"request": request, "current_user": None, "error": error},
        )

    access_token = create_access_token(user.id)

    if user.is_superuser or user.is_admin:
        redirect_url = "/admin"
    else:
        redirect_url = "/"

    redirect = RedirectResponse(url=redirect_url, status_code=status.HTTP_303_SEE_OTHER)
    redirect.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24,
        path="/",
    )
    return redirect


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_template_user(request, db)
    return templates.TemplateResponse(request, "register.html", {"request": request, "current_user": current_user})


@app.get("/logout")
@app.post("/logout")
async def logout_shortcut(request: Request):
    redirect = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    redirect.delete_cookie(key="access_token", path="/")
    redirect.delete_cookie(key="session", path="/")
    return redirect


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, db: AsyncSession = Depends(get_db)):
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

    if current_user is None or not current_user.is_active:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    if not (current_user.is_admin or current_user.is_superuser):
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    return templates.TemplateResponse(
        request,
        "admin.html",
        {"request": request, "current_user": current_user},
    )


def create_access_token(subject: str | int, expires_delta: timedelta | None = None) -> str:
    if expires_delta is None:
        expires_delta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    expire = datetime.now(timezone.utc) + expires_delta
    payload = {"sub": str(subject), "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    db: AsyncSession = Depends(get_db),
    access_token_cookie: str | None = Cookie(default=None),
) -> User:
    token_value = None

    if credentials is not None and credentials.credentials:
        token_value = credentials.credentials
    elif access_token_cookie:
        token_value = access_token_cookie.replace("Bearer ", "").strip()

    if token_value is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization required")

    payload = decode_access_token(token_value)
    user_id = payload.get("sub")
    if user_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is missing user id")

    user = await db.get(User, int(user_id))
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_admin and not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


async def get_current_superuser(current_user: User = Depends(get_current_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Superuser access required")
    return current_user


async def send_telegram_message(text: str) -> None:
    if TELEGRAM_BOT_TOKEN == "mock_token" or TELEGRAM_CHAT_ID == "mock_id":
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text}
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            await client.post(url, data=payload)
        except httpx.HTTPError:
            return


async def calculate_average_rating_for_product(session: AsyncSession, product_id: int) -> float:
    result = await session.execute(
        select(func.avg(Review.rating).label("average_rating")).where(Review.product_id == product_id)
    )
    average = result.scalar_one_or_none()
    return round(float(average), 2) if average is not None else 0.0


async def product_response_with_average(session: AsyncSession, product: Product) -> ProductOut:
    avg = await calculate_average_rating_for_product(session, product.id)
    return ProductOut(
        id=product.id,
        title=product.title,
        description=product.description,
        price=product.price,
        stock_quantity=product.stock_quantity,
        image_url=product.image_url,
        video_url=product.video_url,
        status=product.status,
        user_id=product.user_id,
        admin_id=product.admin_id,
        date_created=product.date_created,
        average_rating=avg,
    )




@app.get("/api/v1/auth/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@app.get("/api/v1/products/", response_model=list[ProductOut])
async def get_products(
    min_price: int | None = Query(None, ge=0),
    max_price: int | None = Query(None, ge=0),
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    size: int = Query(12, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product)

    if min_price is not None:
        stmt = stmt.where(Product.price >= min_price)
    if max_price is not None:
        stmt = stmt.where(Product.price <= max_price)
    if search:
        stmt = stmt.where(Product.title.ilike(f"%{search}%"))

    stmt = stmt.order_by(Product.date_created.desc()).offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    products = result.scalars().all()

    response = []
    for product in products:
        response.append(await product_response_with_average(db, product))
    return response


@app.get("/api/v1/products/{product_id}", response_model=ProductDetailOut)
async def get_product(product_id: int, db: AsyncSession = Depends(get_db)):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    reviews = (await db.execute(
        select(Review).where(Review.product_id == product_id).order_by(Review.created_at.desc())
    )).scalars().all()

    review_out = [
        ReviewOut(
            id=review.id,
            product_id=review.product_id,
            user_id=review.user_id,
            rating=review.rating,
            comment=review.comment,
            created_at=review.created_at,
            username=(await db.get(User, review.user_id)).username if await db.get(User, review.user_id) else None,
        )
        for review in reviews
    ]

    average_rating = await calculate_average_rating_for_product(db, product_id)
    return ProductDetailOut(
        id=product.id,
        title=product.title,
        description=product.description,
        price=product.price,
        stock_quantity=product.stock_quantity,
        image_url=product.image_url,
        video_url=product.video_url,
        status=product.status,
        user_id=product.user_id,
        admin_id=product.admin_id,
        date_created=product.date_created,
        average_rating=average_rating,
        reviews=review_out,
    )


@app.post("/api/v1/products/", response_model=ProductOut, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    product = Product(
        title=payload.title,
        description=payload.description,
        price=payload.price,
        stock_quantity=payload.stock_quantity,
        image_url=payload.image_url,
        video_url=payload.video_url,
        status=payload.status or "approved",
        user_id=current_user.id,
        admin_id=current_user.id,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return await product_response_with_average(db, product)




@app.post("/api/v1/upload/photo", response_model=UploadResponse)
async def upload_photo(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Only image files are allowed")

    safe_name = Path(file.filename or f"{uuid4().hex}.png").name
    file_path = PHOTO_DIR / safe_name
    content = await file.read()
    file_path.write_bytes(content)
    return UploadResponse(url=f"/uploads/photos/{safe_name}")


@app.post("/api/v1/upload/video", response_model=UploadResponse)
async def upload_video(file: UploadFile = File(...)):
    if not file.content_type or not file.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="Only video files are allowed")

    safe_name = Path(file.filename or f"{uuid4().hex}.mp4").name
    file_path = VIDEO_DIR / safe_name
    content = await file.read()
    file_path.write_bytes(content)
    return UploadResponse(url=f"/uploads/videos/{safe_name}")


@app.get("/api/v1/resume/", response_model=list[ResumeOut])
async def get_resumes(db: AsyncSession = Depends(get_db)):
    resumes = (await db.execute(select(Resume).order_by(Resume.created_at.desc()))).scalars().all()
    return resumes


@app.post("/api/v1/resume/", response_model=ResumeOut, status_code=status.HTTP_201_CREATED)
async def upsert_resume(
    payload: ResumeCreate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    existing = await db.scalar(select(Resume).where(and_(Resume.name == payload.name, Resume.role == payload.role)))
    if existing:
        existing.bio = payload.bio
        await db.commit()
        await db.refresh(existing)
        return existing

    resume = Resume(name=payload.name, role=payload.role, bio=payload.bio)
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    return resume


@app.get("/api/v1/admin/users", response_model=list[UserPublic])
async def get_all_users(current_user: User = Depends(get_current_superuser), db: AsyncSession = Depends(get_db)):
    users = (await db.execute(select(User).order_by(User.id))).scalars().all()
    return users


@app.patch("/api/v1/admin/users/{user_id}/role", response_model=UserPublic)
async def update_user_role(
    user_id: int,
    payload: dict,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_admin = bool(payload.get("is_admin", user.is_admin))
    await db.commit()
    await db.refresh(user)
    return user


@app.get("/api/v1/admin/orders", response_model=list[OrderOut])
async def admin_get_orders(current_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    orders = (await db.execute(select(Order).order_by(Order.created_at.desc()))).scalars().all()
    result = []
    for order in orders:
        items = (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
        result.append(
            OrderOut(
                id=order.id,
                user_id=order.user_id,
                total_price=order.total_price,
                status=order.status,
                created_at=order.created_at,
                items=[
                    {
                        "id": item.id,
                        "order_id": item.order_id,
                        "product_id": item.product_id,
                        "quantity": item.quantity,
                        "price_at_purchase": item.price_at_purchase,
                        "product_title": (await db.get(Product, item.product_id)).title if await db.get(Product, item.product_id) else None,
                    }
                    for item in items
                ],
            )
        )
    return result


@app.patch("/api/v1/admin/orders/{order_id}/status", response_model=OrderOut)
async def update_order_status(
    order_id: int,
    payload: OrderStatusUpdate,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    order = await db.get(Order, order_id)
    if order is None:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = payload.status
    await db.commit()
    await db.refresh(order)

    items = (await db.execute(select(OrderItem).where(OrderItem.order_id == order.id))).scalars().all()
    return OrderOut(
        id=order.id,
        user_id=order.user_id,
        total_price=order.total_price,
        status=order.status,
        created_at=order.created_at,
        items=[
            {
                "id": item.id,
                "order_id": item.order_id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "price_at_purchase": item.price_at_purchase,
                "product_title": (await db.get(Product, item.product_id)).title if await db.get(Product, item.product_id) else None,
            }
            for item in items
        ],
    )


@app.get("/api/v1/admin/complaints", response_model=list[ComplaintOut])
async def admin_get_complaints(current_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    complaints = (await db.execute(select(Complaint).order_by(Complaint.created_at.desc()))).scalars().all()
    return complaints


@app.get("/api/v1/admin/stats", response_model=StatsOut)
async def admin_stats(current_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    revenue_result = await db.execute(select(func.coalesce(func.sum(Order.total_price), 0)).select_from(Order))
    order_count_result = await db.execute(select(func.count(Order.id)).select_from(Order))
    total_revenue = int(revenue_result.scalar_one() or 0)
    total_orders = int(order_count_result.scalar_one() or 0)
    return StatsOut(total_revenue=total_revenue, total_orders=total_orders)


@app.get("/api/v1/health")
async def health_check():
    return {"status": "ok"}
