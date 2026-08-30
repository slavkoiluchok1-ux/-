import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

DEFAULT_DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./fastmoney.db")
DATABASE_URL = DEFAULT_DATABASE_URL

if "localhost" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.replace("localhost", "127.0.0.1")

Base = declarative_base()


class DatabaseUnavailableError(RuntimeError):
    pass


connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_async_engine(DATABASE_URL, echo=False, future=True, connect_args=connect_args)

async_session = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def ensure_resume_table_columns() -> None:
    async with engine.begin() as connection:
        if DATABASE_URL.startswith("sqlite"):
            try:
                table_check = await connection.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name='resumes'")
                )
                if table_check.fetchone() is None:
                    await connection.run_sync(Base.metadata.create_all)
                    return

                columns = await connection.execute(text("PRAGMA table_info(resumes)"))
                existing = {row[1] for row in columns.fetchall()}

                required_columns = {
                    "title": "VARCHAR(200)",
                    "specialty": "VARCHAR(200)",
                    "experience_years": "VARCHAR(80)",
                    "experience": "VARCHAR(255)",
                    "skills": "TEXT",
                    "bio": "TEXT",
                    "summary": "TEXT",
                    "cv_file_path": "VARCHAR(500)",
                    "public_contacts": "TEXT",
                    "display_name": "VARCHAR(120)",
                    "phone": "VARCHAR(50)",
                    "viber": "VARCHAR(80)",
                    "telegram": "VARCHAR(80)",
                    "instagram": "VARCHAR(80)",
                    "whatsapp": "VARCHAR(80)",
                    "public_email": "VARCHAR(255)",
                    "updated_at": "DATETIME",
                    "status": "VARCHAR(30) DEFAULT 'active'",
                }

                for column_name, column_type in required_columns.items():
                    if column_name not in existing:
                        await connection.execute(
                            text(f"ALTER TABLE resumes ADD COLUMN {column_name} {column_type}")
                        )
            except Exception:
                pass

        else:
            try:
                result = await connection.execute(
                    text("SELECT column_name FROM information_schema.columns WHERE table_name = 'users'")
                )
                columns = {row[0] for row in result.fetchall()}
                if "hashed_password" not in columns:
                    await connection.execute(text("ALTER TABLE users ADD COLUMN hashed_password VARCHAR(255)"))
            except Exception:
                pass


async def ensure_order_table_columns() -> None:
    async with engine.begin() as connection:
        if not DATABASE_URL.startswith("sqlite"):
            return

        try:
            table_check = await connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='orders'")
            )
            if table_check.fetchone() is None:
                return

            columns = await connection.execute(text("PRAGMA table_info(orders)"))
            existing = {row[1] for row in columns.fetchall()}

            required_columns = {
                "delivery_address": "VARCHAR(500) DEFAULT ''",
                "payment_method": "VARCHAR(100) DEFAULT 'Оплата при отриманні'",
                "phone": "VARCHAR(50) DEFAULT ''",
            }

            for column_name, column_def in required_columns.items():
                if column_name not in existing:
                    await connection.execute(text(f"ALTER TABLE orders ADD COLUMN {column_name} {column_def}"))
        except Exception:
            pass


async def ensure_schema() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with engine.begin() as connection:
        if DATABASE_URL.startswith("sqlite"):
            users_columns = await connection.execute(text("PRAGMA table_info(users)"))
            user_existing = {row[1] for row in users_columns.fetchall()}
            if "is_banned" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN is_banned BOOLEAN DEFAULT 0 NOT NULL"))
            if "banned_until" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN banned_until DATETIME NULL"))
            if "tg_link_code" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN tg_link_code VARCHAR(30) NULL"))
            if "telegram_chat_id" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN telegram_chat_id VARCHAR(80) NULL"))
            if "first_name" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN first_name VARCHAR(80) NULL"))
            if "last_name" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN last_name VARCHAR(80) NULL"))
            if "birth_date" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN birth_date DATE NULL"))
            if "is_age_locked" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN is_age_locked BOOLEAN DEFAULT 0 NOT NULL"))
            if "avatar_url" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500) NULL"))
            if "last_login_ip" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN last_login_ip VARCHAR(64) NULL"))
            if "last_login_at" not in user_existing:
                await connection.execute(text("ALTER TABLE users ADD COLUMN last_login_at DATETIME NULL"))

            products_columns = await connection.execute(text("PRAGMA table_info(products)"))
            product_existing = {row[1] for row in products_columns.fetchall()}
            if "category_id" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN category_id INTEGER NULL"))
            if "seller_phone" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN seller_phone VARCHAR(80) NULL"))
            if "sales_count" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN sales_count INTEGER NOT NULL DEFAULT 0"))
            if "product_type" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN product_type VARCHAR(30) NOT NULL DEFAULT 'physical'"))
            if "sku" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN sku VARCHAR(80) NULL"))
            if "sale_price" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN sale_price INTEGER NULL"))
            if "is_draft" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN is_draft BOOLEAN NOT NULL DEFAULT 0"))
            if "tags" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN tags TEXT NULL"))
            if "attributes" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN attributes TEXT NULL"))
            if "digital_content" not in product_existing:
                await connection.execute(text("ALTER TABLE products ADD COLUMN digital_content TEXT NULL"))

            try:
                await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_products_sku ON products(sku) WHERE sku IS NOT NULL"))
            except Exception:
                pass

            try:
                await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_cart_user_product ON cart_items(user_id, product_id)"))
            except Exception:
                pass

            try:
                await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS uq_favorite_user_product ON favorites(user_id, product_id)"))
            except Exception:
                pass

            await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_tg_link_code ON users(tg_link_code) WHERE tg_link_code IS NOT NULL"))
            await connection.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_telegram_chat_id ON users(telegram_chat_id) WHERE telegram_chat_id IS NOT NULL"))

            complaints_columns = await connection.execute(text("PRAGMA table_info(complaints)"))
            complaint_existing = {row[1] for row in complaints_columns.fetchall()}
            if "target_user_id" not in complaint_existing:
                await connection.execute(text("ALTER TABLE complaints ADD COLUMN target_user_id INTEGER NULL"))

    await ensure_resume_table_columns()
    await ensure_order_table_columns()
    await seed_default_categories()


async def seed_default_categories() -> None:
    from models import Category

    async with async_session() as db:
        existing_count = await db.scalar(select(func.count()).select_from(Category))
        if existing_count and existing_count > 0:
            return

        seed_data = [
            {
                "name": "Електроніка",
                "slug": "elektronika",
                "icon": "📱",
                "children": [
                    {"name": "Смартфони", "slug": "smartfony"},
                    {"name": "Ноутбуки", "slug": "noutbuki"},
                    {"name": "Комплектуючі", "slug": "komplektuyuchi"},
                    {"name": "Аксесуари", "slug": "aksesuary"},
                ],
            },
            {
                "name": "Одяг та взуття",
                "slug": "odyag-ta-vzuttya",
                "icon": "👕",
                "children": [
                    {"name": "Чоловічий", "slug": "cholovichiy"},
                    {"name": "Жіночий", "slug": "zhinochiy"},
                    {"name": "Дитячий", "slug": "dityachiy"},
                    {"name": "Взуття", "slug": "vzuttia"},
                ],
            },
            {
                "name": "Дім та сад",
                "slug": "dim-ta-sad",
                "icon": "🏡",
                "children": [
                    {"name": "Меблі", "slug": "mebli"},
                    {"name": "Декор", "slug": "dekor"},
                    {"name": "Інструменти", "slug": "instrumenty"},
                    {"name": "Посуд", "slug": "posud"},
                ],
            },
            {
                "name": "Цифрові товари",
                "slug": "tsyfrovi-tovary",
                "icon": "🎮",
                "children": [
                    {"name": "Ігри", "slug": "igry"},
                    {"name": "Софт", "slug": "soft"},
                    {"name": "Акаунти", "slug": "rahunky"},
                    {"name": "Курси", "slug": "kursy"},
                ],
            },
            {
                "name": "Автотовари",
                "slug": "avtotovary",
                "icon": "🚗",
                "children": [
                    {"name": "Запчастини", "slug": "zapchastyny"},
                    {"name": "Автохімія", "slug": "avtokhimiya"},
                    {"name": "Салон", "slug": "salon"},
                ],
            },
            {
                "name": "Спорт та відпочинок",
                "slug": "sport-ta-vidpochynok",
                "icon": "⚽️",
                "children": [
                    {"name": "Тренажери", "slug": "trenazhery"},
                    {"name": "Туризм", "slug": "turystychni-tovary"},
                    {"name": "Велосипеди", "slug": "velosyped"},
                ],
            },
            {
                "name": "Краса та здоров'я",
                "slug": "krasa-ta-zdorovya",
                "icon": "💄",
                "children": [
                    {"name": "Косметика", "slug": "kosmetyka"},
                    {"name": "Парфумерія", "slug": "parfumeriya"},
                    {"name": "Догляд", "slug": "dohlyad"},
                ],
            },
            {
                "name": "Крафт та Хендмейд",
                "slug": "kraft-ta-hendmeyd",
                "icon": "🎨",
                "children": [
                    {"name": "Прикраси", "slug": "prykrasy"},
                    {"name": "Декор ручної роботи", "slug": "dekor-ruchnoyi-roboty"},
                ],
            },
        ]

        for parent_data in seed_data:
            parent = Category(name=parent_data["name"], slug=parent_data["slug"], icon=parent_data["icon"])
            db.add(parent)
            await db.flush()
            for child_data in parent_data.get("children", []):
                db.add(Category(name=child_data["name"], slug=child_data["slug"], parent_id=parent.id))

        await db.commit()


async def cleanup_html_redirect_product() -> None:
    redirect_pattern = "%HTML redirect product%"
    async with async_session() as db:
        await db.execute(
            text(
                "DELETE FROM cart_items WHERE product_id IN ("
                "SELECT id FROM products WHERE title LIKE :pattern"
                ")"
            ),
            {"pattern": redirect_pattern},
        )
        await db.execute(
            text(
                "DELETE FROM order_items WHERE product_id IN ("
                "SELECT id FROM products WHERE title LIKE :pattern"
                ")"
            ),
            {"pattern": redirect_pattern},
        )
        await db.execute(
            text(
                "DELETE FROM favorites WHERE product_id IN ("
                "SELECT id FROM products WHERE title LIKE :pattern"
                ")"
            ),
            {"pattern": redirect_pattern},
        )
        await db.execute(
            text("DELETE FROM products WHERE title LIKE :pattern"),
            {"pattern": redirect_pattern},
        )
        await db.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    await ensure_schema()
    async with async_session() as session:
        yield session
