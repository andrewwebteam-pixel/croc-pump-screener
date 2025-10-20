import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

from config import TELEGRAM_TOKEN
from database import init_db, activate_key, check_subscription

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализация базы данных
init_db()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Проверяем, активен ли уже ключ для пользователя
    username = message.from_user.username or str(message.from_user.id)
    if check_subscription(username):
        await message.answer(
            "Welcome back! 🎉 Your subscription is active. Use the menu to configure alerts."
        )
    else:
        await message.answer(
            "Hello! 👋 To use this bot you need to activate your access key.\n"
            "Please send /activate <your-key> to start."
        )

@dp.message(Command("activate"))
async def cmd_activate(message: Message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Usage: /activate <key> 🗝️")
        return
    access_key = parts[1]
    username = message.from_user.username or str(message.from_user.id)
    if activate_key(access_key, username):
        await message.answer("Your key has been activated successfully! ✅")
    else:
        await message.answer(
            "Invalid key or this key has already been used by another user. ❌"
        )

@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Here are the available commands 📋:\n"
        "/start — Start the bot and get activation instructions.\n"
        "/activate <key> — Activate your access key.\n"
        "/help — Show this help message."
    )

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
