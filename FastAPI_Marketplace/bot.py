from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx
from sqlalchemy import select

from database import async_session
from models import User

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "mock_token")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "FastMoneyMarketBot")


async def send_message(
    chat_id: str | int | None,
    text: str,
    reply_markup: dict[str, Any] | None = None,
    parse_mode: str = "HTML",
) -> bool:
    if not chat_id or BOT_TOKEN in {"mock_token", "mock_id"}:
        return False

    try:
        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
            return bool(result.get("ok"))
    except Exception as exc:
        logger.warning("Telegram sendMessage failed: %s", exc)
        return False


async def send_telegram_notification(chat_id: int | str | None, message: str) -> bool:
    if not chat_id:
        return False
    try:
        return await send_message(str(chat_id), message)
    except Exception:
        return False


async def notify_admins_about_new_report(report_id: int, reason: str, reporter_name: str | None = None) -> bool:
    async with async_session() as session:
        result = await session.execute(
            select(User)
            .where((User.is_admin.is_(True)) | (User.is_superuser.is_(True)))
            .where(User.telegram_chat_id.isnot(None))
        )
        admins = result.scalars().all()

    if not admins:
        return False

    reporter_label = (reporter_name or "Користувач").strip() or "Користувач"
    text = (
        f"🚨 Нова скарга №{report_id}! Причина: {reason}. "
        f"Скаргник: {reporter_label}. Перевірте в адмін-панелі."
    )

    sent_any = False
    for admin in admins:
        ok = await send_message(getattr(admin, "telegram_chat_id", None), text)
        sent_any = sent_any or ok
    return sent_any
