import os
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy import text
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

    await ensure_resume_table_columns()
    await ensure_order_table_columns()


async def cleanup_html_redirect_product() -> None:
    async with async_session() as db:
        await db.execute(
            text(
                "DELETE FROM cart_items WHERE product_id IN ("
                "SELECT id FROM products WHERE title LIKE '%HTML redirect product%' "
                "OR name LIKE '%HTML redirect product%'"
                ")"
            )
        )
        await db.execute(
            text(
                "DELETE FROM order_items WHERE product_id IN ("
                "SELECT id FROM products WHERE title LIKE '%HTML redirect product%' "
                "OR name LIKE '%HTML redirect product%'"
                ")"
            )
        )
        await db.execute(
            text(
                "DELETE FROM favorites WHERE product_id IN ("
                "SELECT id FROM products WHERE title LIKE '%HTML redirect product%' "
                "OR name LIKE '%HTML redirect product%'"
                ")"
            )
        )
        await db.execute(
            text(
                "DELETE FROM products WHERE title LIKE '%HTML redirect product%' "
                "OR name LIKE '%HTML redirect product%'"
            )
        )
        await db.commit()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        yield session
