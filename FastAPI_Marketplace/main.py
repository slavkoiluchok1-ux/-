from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager, suppress
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

import httpx
import jwt
from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from passlib.context import CryptContext
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot import (
    ensure_user_tg_link_code,
    notify_seller_order_purchase,
    notify_seller_stockout,
    send_telegram_notification,
    start_bot,
    start_bot_polling,
)
from services.scheduler import run_daily_age_check_loop
from database import Base, DatabaseUnavailableError, async_session, cleanup_html_redirect_product, engine, ensure_schema, get_db
from dependencies import get_current_admin_user, get_current_superuser, get_current_user
from models import CartItem, Complaint, Favorite, Order, OrderItem, Portfolio, Product, Report, Review, Resume, User
from routers.auth import router as auth_router
from routers.cart import router as cart_router
from routers.catalog import router as catalog_router, ensure_default_categories
from routers.categories import router as categories_router
from routers.complaints import router as complaints_router
from routers.favorites import router as favorites_router
from routers.orders import router as orders_router
from routers.portfolio import router as portfolio_router
from routers.profile import router as profile_router
from routers.admin import router as admin_router
from routers.reports import router as reports_router
from routers.users import router as users_router
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
    SellerSalesAnalyticsOut,
    StatsOut,
    Token,
    UploadResponse,
    UserCreate,
    UserLogin,
    UserPublic,
    UserRoleUpdate,
)


logger = logging.getLogger(__name__)
TELEGRAM_POLL_TASK: asyncio.Task | None = None
AGE_CHECK_TASK: asyncio.Task | None = None

APP_BRAND = "Fast Money"
DB_UNAVAILABLE_MESSAGE = "База даних тимчасово недоступна. Перевірте DATABASE_URL у .env і стан запущеного сервера бази даних (SQLite або PostgreSQL)."

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
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8049369382:AAERtZx8aBaZADqjkc2lu6UKmMVQXBXc7TQ")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "mock_id")
TELEGRAM_BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "FastMoneyMarketBot")
BOT_USERNAME = TELEGRAM_BOT_USERNAME
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
    global TELEGRAM_POLL_TASK, AGE_CHECK_TASK
    try:
        await create_db_tables()
        await cleanup_html_redirect_product()
        await ensure_superadmin()
        try:
            async with async_session() as session:
                await ensure_default_categories(session)
        except Exception as cat_exc:
            logger.warning("Не вдалось створити категорії за замовчуванням: %s", cat_exc)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_TOKEN not in {"mock_token", "mock_id"}:
            TELEGRAM_POLL_TASK = asyncio.create_task(start_bot())
        AGE_CHECK_TASK = asyncio.create_task(run_daily_age_check_loop())
    except Exception as exc:
        logger.warning(
            "Помилка підключення до БД. Перевірте налаштування .env та запуск PostgreSQL. Деталі: %s",
            exc,
        )
    yield
    if TELEGRAM_POLL_TASK is not None:
        TELEGRAM_POLL_TASK.cancel()
        with suppress(asyncio.CancelledError):
            await TELEGRAM_POLL_TASK
    if AGE_CHECK_TASK is not None:
        AGE_CHECK_TASK.cancel()
        with suppress(asyncio.CancelledError):
            await AGE_CHECK_TASK

app = FastAPI(
    title=APP_BRAND,
    version="1.0.0",
    lifespan=lifespan,
)


def get_age_in_years(birth_date: date | None) -> int | None:
    if birth_date is None:
        return None
    today = date.today()
    age = today.year - birth_date.year - ((today.month, today.day) < (birth_date.month, birth_date.day))
    return age


def get_age_lock_date(birth_date: date | None) -> date | None:
    if birth_date is None:
        return None
    return birth_date.replace(year=birth_date.year + 18)


@app.middleware("http")
async def age_gate_middleware(request: Request, call_next):
    if request.method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return await call_next(request)

    if request.url.path in {"/login", "/register", "/logout", "/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/logout", "/api/v1/auth/csrf", "/age-locked"}:
        return await call_next(request)

    if request.url.path.startswith("/static") or request.url.path.startswith("/uploads") or request.url.path.startswith("/api/"):
        return await call_next(request)

    token_value = request.cookies.get("access_token")
    if not token_value:
        return await call_next(request)

    try:
        payload = decode_access_token(token_value.replace("Bearer ", "").strip())
    except HTTPException:
        return await call_next(request)

    user_id = payload.get("sub")
    if user_id is None:
        return await call_next(request)

    db = async_session()
    try:
        async with db as session:
            user = await session.get(User, int(user_id))
            if user is not None and user.is_age_locked:
                return RedirectResponse(url="/age-locked", status_code=status.HTTP_303_SEE_OTHER)
    finally:
        await db.close()

    return await call_next(request)


@app.middleware("http")
async def csrf_middleware(request: Request, call_next):
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)

    if path in {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/logout", "/api/v1/auth/csrf"}:
        return await call_next(request)

    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token") or request.headers.get("x-csrf-token")
    if cookie_token and header_token and cookie_token == header_token:
        return await call_next(request)

    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return await call_next(request)

    if request.headers.get("authorization") or request.headers.get("Authorization"):
        return await call_next(request)

    if not cookie_token:
        return await call_next(request)

    # For standard browser submissions, allow if session cookie or valid headers
    return await call_next(request)


app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(categories_router)
app.include_router(cart_router)
app.include_router(orders_router)
app.include_router(favorites_router)
app.include_router(complaints_router)
app.include_router(portfolio_router)
app.include_router(profile_router)
app.include_router(admin_router)
app.include_router(reports_router)
app.include_router(users_router)


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
        user = await db.get(User, int(user_id))
        if user is not None:
            await ensure_user_tg_link_code(user, db)
        return user
    except HTTPException:
        return None


@app.get("/", response_class=HTMLResponse)
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_template_user(request, db)
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "request": request,
            "current_user": current_user,
            "BOT_USERNAME": BOT_USERNAME,
            "is_authenticated": current_user is not None,
        },
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


@app.get("/age-locked", response_class=HTMLResponse)
async def age_locked_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_template_user(request, db)
    if current_user is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)

    lock_date = get_age_lock_date(current_user.birth_date)
    return templates.TemplateResponse(
        request,
        "age_locked.html",
        {
            "request": request,
            "current_user": current_user,
            "lock_date": lock_date,
            "telegram_bot_link": "https://t.me/FastMoneyMarketBot",
        },
    )


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


async def _user_has_sales(db: AsyncSession, user_id: int) -> bool:
    result = await db.execute(
        select(OrderItem.id)
        .join(Product, Product.id == OrderItem.product_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(Product.user_id == user_id)
        .where(Order.status != "cancelled")
        .limit(1)
    )
    return result.scalar() is not None


@app.get("/api/v1/auth/me", response_model=UserPublic)
async def get_me(current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return UserPublic(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        is_active=current_user.is_active,
        is_admin=current_user.is_admin,
        is_superuser=current_user.is_superuser,
        is_banned=current_user.is_banned,
        banned_until=current_user.banned_until,
        display_name=current_user.display_name,
        phone=current_user.phone,
        created_at=current_user.created_at,
        has_sales=await _user_has_sales(db, current_user.id),
    )




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
async def get_all_users(
    q: str | None = None,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).order_by(User.id)
    if q and q.strip():
        term = f"%{q.strip()}%"
        stmt = stmt.where(User.username.ilike(term))
    users = (await db.execute(stmt)).scalars().all()
    return users


@app.patch("/api/v1/admin/users/{user_id}/role", response_model=UserPublic)
async def update_user_role(
    user_id: int,
    payload: UserRoleUpdate,
    current_user: User = Depends(get_current_superuser),
    db: AsyncSession = Depends(get_db),
):
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")

    if user.is_superuser or getattr(user, "role", None) == "superadmin" or user.id == 1:
        raise HTTPException(status_code=400, detail="Неможливо змінити роль супер адміністратора")

    original_username = user.username
    user.is_admin = bool(payload.is_admin)
    user.username = original_username

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

    normalized_status = payload.status
    if normalized_status == "new":
        normalized_status = "created"

    order.status = normalized_status
    await db.commit()
    await db.refresh(order)

    status_labels = {
        "created": "Нове",
        "new": "Нове",
        "paid": "Оплачено",
        "shipped": "Відправлено",
        "completed": "Виконано",
        "cancelled": "Скасовано",
    }
    buyer = await db.get(User, order.user_id)
    if buyer and buyer.telegram_chat_id:
        await send_telegram_notification(
            buyer.telegram_chat_id,
            f"📦 Статус замовлення №{order.id} змінено на: {status_labels.get(order.status, order.status)}",
        )

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


REASON_LABELS = {
    "profanity": "Нецензурна лексика",
    "threats": "Погрози",
    "sexual": "Контент сексуального характеру",
    "fraud": "Шахрайство",
    "spam": "Спам / Реклама",
    "other": "Інше",
}


def format_reason_label(reason: str | None) -> str:
    if not reason:
        return "Інше"
    return REASON_LABELS.get(reason, reason)


@app.get("/api/v1/admin/complaints", response_model=list[ComplaintOut])
async def admin_get_complaints(current_user: User = Depends(get_current_admin), db: AsyncSession = Depends(get_db)):
    complaints = (await db.execute(select(Complaint).order_by(Complaint.created_at.desc()))).scalars().all()
    result = []
    for item in complaints:
        reporter = await db.get(User, item.reporter_id)
        product = await db.get(Product, item.target_id) if item.target_type == "product" else None
        comment = await db.get(Review, item.target_id) if item.target_type == "comment" else None
        complaint_data = ComplaintOut.model_validate(item)
        complaint_data.user_id = item.reporter_id
        complaint_data.product_id = item.target_id if item.target_type == "product" else None
        complaint_data.target_user_id = item.target_user_id or (comment.user_id if comment else None)
        complaint_data.username = reporter.username if reporter else None
        complaint_data.user_email = reporter.email if reporter else None
        complaint_data.subject = format_reason_label(item.reason)
        complaint_data.title = complaint_data.subject
        complaint_data.text = item.comment or ""
        complaint_data.target_text = comment.comment if comment else None
        if item.target_type == "product" and product is not None:
            complaint_data.object_label = f'Товар "{product.title}" (ID: {product.id})'
        elif item.target_type == "comment" and comment is not None:
            author = await db.get(User, comment.user_id)
            complaint_data.object_label = f'Коментар "{(comment.comment or "").strip()[:120]}" (ID: {comment.id})'
            complaint_data.username = author.username if author else complaint_data.username
        elif reporter is not None:
            complaint_data.object_label = f'Користувач "{reporter.username}" (ID: {reporter.id})'
        result.append(complaint_data)
    return result


@app.post("/api/v1/admin/users/{user_id}/ban", response_model=UserPublic)
async def ban_user_by_admin(
    user_id: int,
    payload: dict | None = None,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    target = await db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="User not found")
    if target.is_superuser or target.role == "superadmin" or target.id == 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Заборонено банити головного адміністратора (Superadmin)")
    if target.id == current_user.id:
        raise HTTPException(status_code=403, detail="Cannot ban yourself")
    if target.is_admin and not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Only superadmin can ban admins")

    duration_raw = (payload or {}).get("duration") if isinstance(payload, dict) else None
    if duration_raw in {"1d", "7d", "30d", "365d"}:
        mapping = {"1d": timedelta(days=1), "7d": timedelta(days=7), "30d": timedelta(days=30), "365d": timedelta(days=365)}
        target.banned_until = datetime.now(timezone.utc) + mapping[duration_raw]
    elif duration_raw in {"permanent", "forever", "infinity", "0"}:
        target.banned_until = None
    else:
        target.banned_until = datetime.now(timezone.utc) + timedelta(days=7)

    target.is_banned = True
    target.is_active = False
    await db.commit()
    await db.refresh(target)
    return target


@app.delete("/api/v1/admin/products/{product_id}")
async def delete_product_by_admin(
    product_id: int,
    current_user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    product = await db.get(Product, product_id)
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found")

    await db.execute(delete(CartItem).where(CartItem.product_id == product_id))
    await db.execute(delete(Favorite).where(Favorite.product_id == product_id))
    await db.execute(delete(OrderItem).where(OrderItem.product_id == product_id))
    await db.delete(product)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
