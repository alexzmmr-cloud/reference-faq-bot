import asyncio
import logging
import os
import sqlite3
from pathlib import Path

from aiogram import Bot, Dispatcher, F
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import load_dotenv

from db import init_db, save_operator_request
from faq_service import FAQ_ITEMS, find_by_id, find_by_keyword

BASE_DIR = Path(__file__).resolve().parent
PLACEHOLDER_TOKEN = "put_your_bot_token_here"
NOTIFICATION_CHAT_ID_VARS = ("OWNER_CHAT_ID", "ADMIN_CHAT_ID")

OPERATOR_CALLBACK = "operator"
UNKNOWN_TEXT_REPLY = "Не понял вопрос. Выберите тему из кнопок ниже или свяжитесь с оператором."
OPERATOR_PROMPT = "Напишите одним сообщением, что вас интересует — обращение передадим оператору."
OPERATOR_NOT_TEXT_REPLY = "Пришлите, пожалуйста, обращение текстом."
OPERATOR_SAVED_REPLY = "Спасибо, обращение принято. Оператор свяжется с вами."
OPERATOR_SAVE_FAILED_REPLY = "Не получилось сохранить обращение, попробуйте ещё раз чуть позже."
WELCOME_TEXT = "Привет! Я FAQ-бот учебного сервиса. Выберите тему или напишите вопрос текстом."

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dp = Dispatcher()

waiting_for_operator_message: set[int] = set()


def get_notification_chat_ids() -> list[int]:
    chat_ids: list[int] = []

    for env_name in NOTIFICATION_CHAT_ID_VARS:
        raw_value = os.getenv(env_name)
        if not raw_value or raw_value.startswith("put_"):
            continue

        try:
            chat_id = int(raw_value)
        except ValueError as exc:
            raise RuntimeError(f"{env_name} must be an integer chat id") from exc

        if chat_id not in chat_ids:
            chat_ids.append(chat_id)

    if not chat_ids:
        raise RuntimeError(
            "OWNER_CHAT_ID or ADMIN_CHAT_ID is not set. "
            "Add a chat id to .env before running the bot."
        )

    return chat_ids


async def notify_admins(bot: Bot, telegram_user_id: int, username: str | None, message_text: str) -> None:
    username_display = f"@{username}" if username else "без username"
    notification_text = (
        "Новое обращение к оператору\n"
        f"user_id={telegram_user_id}\n"
        f"username={username_display}\n"
        f"text={message_text}"
    )

    for chat_id in get_notification_chat_ids():
        await bot.send_message(chat_id=chat_id, text=notification_text)


def build_faq_keyboard() -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=item["button"], callback_data=f"faq:{item['id']}")]
        for item in FAQ_ITEMS
    ]
    buttons.append([InlineKeyboardButton(text="Связаться с оператором", callback_data=OPERATOR_CALLBACK)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


@dp.message(CommandStart())
async def handle_start(message: Message) -> None:
    waiting_for_operator_message.discard(message.from_user.id)
    await message.answer(WELCOME_TEXT, reply_markup=build_faq_keyboard())


@dp.callback_query(F.data.startswith("faq:"))
async def handle_faq_callback(callback: CallbackQuery) -> None:
    faq_id = callback.data.split(":", 1)[1]
    item = find_by_id(faq_id)
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    if item is None:
        await callback.message.answer(UNKNOWN_TEXT_REPLY, reply_markup=build_faq_keyboard())
        return
    await callback.message.answer(item["answer"], reply_markup=build_faq_keyboard())


@dp.callback_query(F.data == OPERATOR_CALLBACK)
async def handle_operator_callback(callback: CallbackQuery) -> None:
    await callback.answer()
    if not isinstance(callback.message, Message):
        return
    waiting_for_operator_message.add(callback.from_user.id)
    await callback.message.answer(OPERATOR_PROMPT)


@dp.message(F.text)
async def handle_text(message: Message, bot: Bot) -> None:
    user_id = message.from_user.id

    if user_id in waiting_for_operator_message:
        username = message.from_user.username
        try:
            save_operator_request(user_id, username, message.text)
        except sqlite3.Error:
            logger.exception("Failed to save operator request for user_id=%s", user_id)
            await message.answer(OPERATOR_SAVE_FAILED_REPLY)
            return

        try:
            await notify_admins(bot, user_id, username, message.text)
        except Exception:
            logger.exception("Failed to notify owner/admin about operator request for user_id=%s", user_id)

        waiting_for_operator_message.discard(user_id)
        await message.answer(OPERATOR_SAVED_REPLY, reply_markup=build_faq_keyboard())
        return

    item = find_by_keyword(message.text)
    if item is not None:
        await message.answer(item["answer"], reply_markup=build_faq_keyboard())
        return

    await message.answer(UNKNOWN_TEXT_REPLY, reply_markup=build_faq_keyboard())


@dp.message()
async def handle_non_text(message: Message) -> None:
    if message.from_user.id in waiting_for_operator_message:
        await message.answer(OPERATOR_NOT_TEXT_REPLY)
        return

    await message.answer(UNKNOWN_TEXT_REPLY, reply_markup=build_faq_keyboard())


async def main() -> None:
    load_dotenv(BASE_DIR / ".env")
    token = os.getenv("BOT_TOKEN")
    if not token or token == PLACEHOLDER_TOKEN:
        raise RuntimeError(
            "BOT_TOKEN не задан. Укажите настоящий токен учебного бота в .env перед запуском."
        )
    get_notification_chat_ids()

    init_db()
    # BOT_PROXY нужен там, где api.telegram.org недоступен напрямую
    # (например, на серверах в РФ) — задаётся в .env или в systemd-юните
    proxy = os.getenv("BOT_PROXY")
    session = AiohttpSession(proxy=proxy) if proxy else None
    bot = Bot(token=token, session=session) if session else Bot(token=token)
    logger.info("Starting bot with long polling")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
