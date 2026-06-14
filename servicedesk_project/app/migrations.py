from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

import app.models  # noqa: F401
from app.database import Base


async def _table_columns(conn: AsyncConnection, table: str) -> set[str]:
    result = await conn.execute(text(f"PRAGMA table_info({table})"))
    return {row[1] for row in result.fetchall()}


async def _add_column(conn: AsyncConnection, table: str, column: str, col_type: str, existing: set[str]):
    if column not in existing:
        await conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


SCHEMA_PATCHES: dict[str, dict[str, str]] = {
    "users": {
        "display_name": "VARCHAR",
        "initial_name": "VARCHAR",
        "phone": "VARCHAR",
        "profile_photo": "VARCHAR",
        "is_worker": "BOOLEAN DEFAULT 0",
        "position": "VARCHAR",
        "position_level": "INTEGER DEFAULT 1",
        "role": "VARCHAR DEFAULT 'user'",
        "bio": "TEXT",
    },
    "problems": {
        "desired_date": "VARCHAR",
        "contact_phone": "VARCHAR",
        "contact_email": "VARCHAR",
        "contact_other": "VARCHAR",
        "admin_id": "INTEGER",
        "worker_id": "INTEGER",
        "image_url": "VARCHAR",
        "status": "VARCHAR DEFAULT 'В обробці'",
        "date_created": "DATETIME",
    },
    "admin_responses": {
        "is_read": "BOOLEAN DEFAULT 0",
        "date_responded": "DATETIME",
    },
    "service_records": {
        "parts_used": "VARCHAR",
        "warranty_info": "VARCHAR",
        "date_completed": "DATETIME",
        "work_done": "VARCHAR",
        "problem_id": "INTEGER",
    },
    "users_in_telegram": {
        "tg_code": "VARCHAR",
        "user_tg_id": "VARCHAR",
        "verify_code": "VARCHAR",
        "verify_chat_id": "VARCHAR",
        "user_in_site": "INTEGER",
        "date_created": "DATETIME",
    },
    "problem_messages": {
        "problem_id": "INTEGER",
        "sender_id": "INTEGER",
        "sender_name": "VARCHAR",
        "message": "TEXT",
        "created_at": "DATETIME",
    },
    "support_requests": {
        "title": "VARCHAR",
        "message": "TEXT",
        "user_id": "INTEGER",
        "contact_phone": "VARCHAR",
        "contact_email": "VARCHAR",
        "contact_other": "VARCHAR",
        "status": "VARCHAR DEFAULT 'Нова'",
        "response_message": "TEXT",
        "date_created": "DATETIME",
    },
    "chat_messages": {
        "sender_id": "INTEGER",
        "sender_name": "VARCHAR",
        "message": "TEXT",
        "created_at": "DATETIME",
    },
    "worker_applications": {
        "name": "VARCHAR",
        "email": "VARCHAR",
        "phone": "VARCHAR",
        "message": "TEXT",
        "contact_other": "VARCHAR",
        "status": "VARCHAR DEFAULT 'Очікує'",
        "date_created": "DATETIME",
    },
    "worker_actions": {
        "origin_user_id": "INTEGER",
        "target_user_id": "INTEGER",
        "action_type": "VARCHAR",
        "reason": "TEXT",
        "status": "VARCHAR DEFAULT 'Очікує'",
        "reviewed_by": "INTEGER",
        "date_created": "DATETIME",
    },
}


async def migrate_schema(conn: AsyncConnection):
    await conn.run_sync(Base.metadata.create_all)

    for table, columns in SCHEMA_PATCHES.items():
        existing = await _table_columns(conn, table)
        if not existing:
            continue
        for column, col_type in columns.items():
            await _add_column(conn, table, column, col_type, existing)
