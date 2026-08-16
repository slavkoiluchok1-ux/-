import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class TelegramService:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(self, chat_id: str, text: str) -> bool:
        if not self.token or not chat_id:
            logger.warning("Telegram Bot Token або Chat ID не налаштовано.")
            return False

        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML"
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(url, json=payload)
                return response.status_code == 200
            except Exception as e:
                logger.error(f"Помилка відправки в Telegram: {e}")
                return False

    async def notify_admin_new_order(self, order_id: int, total_price: float, customer_phone: str):
        chat_id = settings.TELEGRAM_ADMIN_CHAT_ID
        if not chat_id:
            return False
        
        text = (
            f"🛒 <b>Нове замовлення №{order_id}</b>\n\n"
            f"💰 Сума: <b>{total_price} грн</b>\n"
            f"📞 Телефон: {customer_phone}\n"
            f"⚡ Перевірте адмін-панель для деталей."
        )
        return await self.send_message(chat_id=chat_id, text=text)

    async def notify_admin_new_complaint(self, complaint_id: int, user_email: str, text_content: str):
        chat_id = settings.TELEGRAM_ADMIN_CHAT_ID
        if not chat_id:
            return False

        text = (
            f"⚠️ <b>Нова скарга №{complaint_id}</b>\n\n"
            f"👤 Від: {user_email}\n"
            f"📝 Текст: {text_content}\n"
        )
        return await self.send_message(chat_id=chat_id, text=text)

telegram_service = TelegramService()
