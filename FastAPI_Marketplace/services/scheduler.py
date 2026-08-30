from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timezone

from sqlalchemy import select

from bot import send_telegram_notification
from database import async_session
from models import User

logger = logging.getLogger(__name__)


async def unlock_age_restricted_accounts() -> None:
    async with async_session() as session:
        users = (await session.execute(
            select(User).where(User.is_age_locked.is_(True)).where(User.birth_date.is_not(None))
        )).scalars().all()

        for user in users:
            if user.birth_date is None:
                continue

            today = date.today()
            age = today.year - user.birth_date.year - ((today.month, today.day) < (user.birth_date.month, user.birth_date.day))
            if age < 18:
                continue

            user.is_age_locked = False
            logger.info("Unlocked age-restricted account for user_id=%s", user.id)
            if user.telegram_chat_id:
                try:
                    await send_telegram_notification(
                        user.telegram_chat_id,
                        "🔓 Вітаємо! Вам виповнилося 18 років. Повний доступ до майданчика успішно активовано!",
                    )
                except Exception as exc:
                    logger.warning("Telegram unlock notification failed for user_id=%s: %s", user.id, exc)

        await session.commit()


async def run_daily_age_check_loop() -> None:
    while True:
        now = datetime.now(timezone.utc)
        next_run = datetime(now.year, now.month, now.day, 0, 1, 0, tzinfo=timezone.utc)
        if now >= next_run:
            next_run = next_run + __import__('datetime').timedelta(days=1)
        wait_seconds = (next_run - now).total_seconds()
        await asyncio.sleep(max(wait_seconds, 1))
        await unlock_age_restricted_accounts()
