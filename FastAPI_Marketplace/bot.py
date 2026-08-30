from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database import async_session
from models import Order, OrderItem, Product, User

logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8049369382:AAERtZx8aBaZADqjkc2lu6UKmMVQXBXc7TQ")
BOT_USERNAME = os.getenv("TELEGRAM_BOT_USERNAME", "FastMoneyMarketBot")


async def generate_unique_tg_link_code(db: AsyncSession) -> str:
    for _ in range(50):
        code = f"TG-{secrets.randbelow(90000) + 10000}"
        existing = await db.scalar(select(User).where(User.tg_link_code == code))
        if existing is None:
            return code
    raise RuntimeError("Не вдалося згенерувати унікальний Telegram код")


async def ensure_user_tg_link_code(user: User, db: AsyncSession) -> User:
    if not user.tg_link_code:
        user.tg_link_code = await generate_unique_tg_link_code(db)
        await db.commit()
    return user


async def tg_api(method: str, payload: dict[str, Any] | None = None, json_mode: bool = False) -> dict[str, Any]:
    if BOT_TOKEN in {"mock_token", "mock_id"}:
        return {"ok": False, "description": "bot disabled"}

    async with httpx.AsyncClient(timeout=15.0) as client:
        if json_mode:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                json=payload or {},
            )
        else:
            response = await client.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                data=payload or {},
            )
        response.raise_for_status()
        return response.json()


async def _find_user_by_tg_code(code: str) -> User | None:
    async with async_session() as session:
        return await session.scalar(select(User).where(User.tg_link_code == code))


async def bind_user_telegram(user_code: str, chat_id: str) -> bool:
    user = await _find_user_by_tg_code(user_code)
    if user is None:
        return False
    if user.telegram_chat_id == chat_id:
        return True

    async with async_session() as session:
        db_user = await session.get(User, user.id)
        if db_user is None:
            return False
        db_user.telegram_chat_id = str(chat_id)
        db_user.tg_link_code = None
        await session.commit()
    return True


async def _menu_keyboard() -> dict[str, Any]:
    return {
        "keyboard": [
            ["📊 Мій прибуток / Продажі"],
            ["📦 Мої товари"],
            ["⚙️ Статус акаунту"],
        ],
        "resize_keyboard": True,
        "one_time_keyboard": False,
    }


async def _send_menu(chat_id: str | int) -> bool:
    return await send_message(chat_id, "✅ Меню бота готове.", reply_markup=await _menu_keyboard())


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
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup is not None:
            payload["reply_markup"] = json.dumps(reply_markup)
        result = await tg_api("sendMessage", payload, json_mode=True)
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


async def _build_sales_report(user_id: int) -> str:
    async with async_session() as session:
        total_result = await session.execute(
            select(func.coalesce(func.sum(OrderItem.quantity * OrderItem.price_at_purchase), 0.0)).join(Order, Order.id == OrderItem.order_id)
            .join(Product, Product.id == OrderItem.product_id)
            .where(Product.user_id == user_id)
            .where(Order.status != "cancelled")
        )
        total_profit = float(total_result.scalar() or 0)

        recent_sales = await session.execute(
            select(OrderItem, Product.title, Order.created_at)
            .join(Product, Product.id == OrderItem.product_id)
            .join(Order, Order.id == OrderItem.order_id)
            .where(Product.user_id == user_id)
            .where(Order.status != "cancelled")
            .order_by(Order.created_at.desc())
            .limit(3)
        )
        recent_rows = recent_sales.all()

    lines = [f"💰 Загальний дохід: {total_profit:,.2f} ₴"]
    if not recent_rows:
        lines.append("Останні продажі: відсутні.")
    else:
        lines.append("📦 Останні 3 продажі:")
        for item, title, created_at in recent_rows:
            lines.append(f"- {title} · {item.quantity} шт. · {created_at.strftime('%d.%m.%Y') if created_at else '—'}")
    return "\n".join(lines)


async def _build_product_status(user_id: int) -> str:
    async with async_session() as session:
        active_count = await session.scalar(
            select(func.count(Product.id)).where(Product.user_id == user_id).where(Product.quantity > 0)
        )
        out_of_stock = await session.execute(
            select(Product.title)
            .where(Product.user_id == user_id)
            .where(Product.quantity == 0)
            .order_by(Product.title.asc())
            .limit(10)
        )
        stock_items = out_of_stock.scalars().all()

    lines = [f"📦 Активних товарів: {active_count or 0}"]
    if stock_items:
        lines.append("⚠️ Товари без залишків:")
        for title in stock_items:
            lines.append(f"- {title}")
    else:
        lines.append("✅ У всіх товарів є залишок.")
    return "\n".join(lines)


async def _build_status_report(user: User) -> str:
    role = "Суперадмін" if user.is_superuser else "Адміністратор" if user.is_admin else "Користувач"
    age_lock = "Так" if getattr(user, "is_age_locked", False) else "Ні"
    binding = "Прив'язано" if user.telegram_chat_id else "Не прив'язано"
    email = user.email or "—"
    return (
        "⚙️ Статус акаунту\n"
        f"Email: {email}\n"
        f"Роль: {role}\n"
        f"Age Lock: {age_lock}\n"
        f"Telegram: {binding}"
    )


async def _handle_bot_command(chat_id: str | int, text: str) -> None:
    cleaned = text.strip()
    if not cleaned:
        return

    if cleaned.startswith("/start"):
        arg = cleaned.replace("/start", "", 1).strip()
        if arg and arg.upper().startswith("TG-"):
            bound = await bind_user_telegram(arg.upper(), str(chat_id))
            if bound:
                async with async_session() as session:
                    user = await session.scalar(select(User).where(User.telegram_chat_id == str(chat_id)))
                    if user is not None:
                        name = user.display_name or user.username or "користувача"
                        await send_message(chat_id, f"🎉 Акаунт {name} успішно прив'язано!", reply_markup=await _menu_keyboard())
                        return
            await send_message(chat_id, "❌ Код не знайдено або вже використаний.")
            return
        async with async_session() as session:
            user = await session.scalar(select(User).where(User.telegram_chat_id == str(chat_id)))
            if user is None:
                await send_message(chat_id, "ℹ️ Відправте або відкрийте посилання з кодом прив'язки для підключення Telegram.")
                return
        await send_message(chat_id, "✅ Telegram-бот активний.", reply_markup=await _menu_keyboard())
        return

    if cleaned == "📊 Мій прибуток / Продажі":
        async with async_session() as session:
            user = await session.scalar(select(User).where(User.telegram_chat_id == str(chat_id)))
            if user is None:
                await send_message(chat_id, "❌ Спочатку прив'яжіть акаунт через код в профілі.")
                return
            report = await _build_sales_report(user.id)
            await send_message(chat_id, report)
        return

    if cleaned == "📦 Мої товари":
        async with async_session() as session:
            user = await session.scalar(select(User).where(User.telegram_chat_id == str(chat_id)))
            if user is None:
                await send_message(chat_id, "❌ Спочатку прив'яжіть акаунт через код в профілі.")
                return
            report = await _build_product_status(user.id)
            await send_message(chat_id, report)
        return

    if cleaned == "⚙️ Статус акаунту":
        async with async_session() as session:
            user = await session.scalar(select(User).where(User.telegram_chat_id == str(chat_id)))
            if user is None:
                await send_message(chat_id, "❌ Спочатку прив'яжіть акаунт через код в профілі.")
                return
            report = await _build_status_report(user)
            await send_message(chat_id, report)
        return


async def start_bot_polling() -> None:
    if BOT_TOKEN in {"mock_token", "mock_id"}:
        logger.info("Telegram bot disabled; polling skipped.")
        return

    logger.info("Telegram bot polling started")
    offset = None
    while True:
        try:
            params: dict[str, Any] = {"timeout": 10}
            if offset is not None:
                params["offset"] = offset
            result = await tg_api("getUpdates", params)
            if not result.get("ok"):
                await asyncio.sleep(2)
                continue

            for update in result.get("result", []):
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue

                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = (message.get("text") or "").strip()
                if not text or not chat_id:
                    continue

                if text.startswith("/"):
                    await _handle_bot_command(chat_id, text)
                    offset = (update.get("update_id", 0) + 1)
                    continue

                if text in {"📊 Мій прибуток / Продажі", "📦 Мої товари", "⚙️ Статус акаунту"}:
                    await _handle_bot_command(chat_id, text)

                offset = (update.get("update_id", 0) + 1)
        except Exception as exc:
            logger.warning("Telegram polling error: %s", exc)
            await asyncio.sleep(5)


async def start_bot() -> None:
    await start_bot_polling()


async def notify_seller_order_purchase(seller_id: int, buyer_username: str, product_title: str, delivery_address: str) -> bool:
    async with async_session() as session:
        seller = await session.get(User, seller_id)
        if seller is None or not seller.telegram_chat_id:
            return False
        message = (
            "<b>Новий продаж</b>\n"
            f"Покупець: {buyer_username}\n"
            f"Товар: {product_title}\n"
            f"Адреса доставки: {delivery_address}"
        )
        return await send_message(seller.telegram_chat_id, message)


async def notify_seller_stockout(seller_id: int, product_title: str) -> bool:
    async with async_session() as session:
        seller = await session.get(User, seller_id)
        if seller is None or not seller.telegram_chat_id:
            return False
        message = f"<b>Увага!</b> Ваші товари <b>{product_title}</b> закінчилися на складі."
        return await send_message(seller.telegram_chat_id, message)
