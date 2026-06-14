import asyncio
import random

from aiogram import Bot, Dispatcher, Router, types
from aiogram.filters import Command
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import async_session, settings
from app.models import Problem, User, Users_in_telegram

BOT_TOKEN = settings.BOT_TOKEN

bot = Bot(token=BOT_TOKEN)
router = Router()
dp = Dispatcher()
dp.include_router(router)


async def send_msg(user_site_id, message_text):
    async with async_session() as session:
        res = await session.execute(
            select(Users_in_telegram).filter(Users_in_telegram.user_in_site == user_site_id)
        )
        user_tg_info = res.scalars().one_or_none()

        if user_tg_info and user_tg_info.user_tg_id:
            try:
                await bot.send_message(chat_id=user_tg_info.user_tg_id, text=message_text)
            except Exception as e:
                print(f"Помилка відправки в Telegram: {e}")


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Вітаю у ServiceDesk Plus!\n\n"
        "1. Надішліть код з сайту (наприклад: SD-1)\n"
        "2. Бот надішле 4 цифри для підтвердження\n"
        "3. Надішліть ці 4 цифри — і акаунт буде прив'язано\n\n"
        "Перевірка заявки: /status 1"
    )


@router.message(Command("status"))
async def cmd_status(message: types.Message):
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Вкажіть номер заявки.\nПриклад: /status 1")
        return

    try:
        problem_id = int(args[1])
    except ValueError:
        await message.answer("Номер заявки має бути числом!")
        return

    async with async_session() as session:
        res = await session.execute(
            select(Problem)
            .filter(Problem.id == problem_id)
            .options(selectinload(Problem.service_record))
        )
        problem = res.scalars().first()

    if not problem:
        await message.answer(f"Заявку №{problem_id} не знайдено.")
        return

    text = (
        f"Заявка №{problem.id}\n"
        f"Пристрій: {problem.title}\n"
        f"Статус: {problem.status}\n"
        f"Опис: {problem.description}\n"
    )

    if problem.service_record:
        text += (
            f"\nВиконані роботи: {problem.service_record.work_done}\n"
            f"Деталі: {problem.service_record.parts_used or 'немає'}\n"
            f"Гарантія: {problem.service_record.warranty_info}\n"
        )

    await message.answer(text)


async def _confirm_link(session, tg_record: Users_in_telegram, chat_id: str):
    tg_record.user_tg_id = chat_id
    tg_record.verify_code = None
    tg_record.verify_chat_id = None
    session.add(tg_record)
    await session.commit()


@router.message()
async def handle_messages(message: types.Message):
    text = (message.text or "").strip()
    chat_id = str(message.chat.id)

    if text.startswith("/"):
        return

    if text.isdigit() and len(text) == 4:
        async with async_session() as session:
            res = await session.execute(
                select(Users_in_telegram).filter(
                    Users_in_telegram.verify_code == text,
                    Users_in_telegram.verify_chat_id == chat_id,
                )
            )
            tg_record = res.scalars().first()
            if not tg_record:
                await message.answer("Невірний код підтвердження. Спочатку надішліть SD-код з сайту.")
                return
            await _confirm_link(session, tg_record, chat_id)
        await message.answer("Успішно приєднано! Сповіщення увімкнено.")
        return

    user_code = text.upper()
    if not user_code.startswith("SD-"):
        await message.answer("Невірний формат. Надішліть код з сайту, наприклад: SD-1")
        return

    try:
        user_site_id = int(user_code.replace("SD-", ""))
    except ValueError:
        await message.answer("Після SD- має бути номер акаунту.")
        return

    async with async_session() as session:
        user_res = await session.execute(select(User).filter(User.id == user_site_id))
        if not user_res.scalars().first():
            await message.answer("Користувача з таким кодом не знайдено на сайті.")
            return

        res = await session.execute(
            select(Users_in_telegram).filter(Users_in_telegram.user_in_site == user_site_id)
        )
        tg_record = res.scalars().one_or_none()
        if not tg_record:
            tg_record = Users_in_telegram(
                user_in_site=user_site_id,
                tg_code=user_code,
            )
            session.add(tg_record)
            await session.flush()

        verify_code = f"{random.randint(1000, 9999)}"
        tg_record.tg_code = user_code
        tg_record.verify_code = verify_code
        tg_record.verify_chat_id = chat_id
        session.add(tg_record)
        await session.commit()

    await message.answer(
        f"Код підтвердження: {verify_code}\n\n"
        f"Надішліть боту ці 4 цифри для завершення прив'язки."
    )


async def start():
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(start())
