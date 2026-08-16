from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
from app.services.telegram_bot import telegram_service

router = APIRouter()

class TestMessageRequest(BaseModel):
    chat_id: str
    message: str

@router.post("/send-test")
async def send_test_message(data: TestMessageRequest, background_tasks: BackgroundTasks):
    background_tasks.add_task(
        telegram_service.send_message,
        chat_id=data.chat_id,
        text=f"🤖 <b>Тестове повідомлення:</b>\n{data.message}"
    )
    return {"status": "success", "message": "Повідомлення додано в чергу відправки"}

@router.post("/webhook")
async def telegram_webhook(update: dict):
    if "message" in update and "chat" in update["message"]:
        chat_id = update["message"]["chat"]["id"]
        text = update["message"].get("text", "")

        if text == "/start":
            welcome_text = (
                f"👋 Вітаємо в <b>ScooterShop Bot</b>!\n\n"
                f"Ваш Chat ID: <code>{chat_id}</code>\n\n"
                f"Скопіюйте цей ID та вставте у змінну <code>TELEGRAM_ADMIN_CHAT_ID</code> у файлі .env"
            )
            await telegram_service.send_message(chat_id=str(chat_id), text=welcome_text)

    return {"ok": True}
