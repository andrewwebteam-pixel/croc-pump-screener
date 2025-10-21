import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

from config import TELEGRAM_TOKEN
from database import init_db, activate_key, check_subscription
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📈 Pump Alerts"),
            KeyboardButton(text="📉 Dump Alerts"),
        ],
        [
            KeyboardButton(text="⚙️ Settings"),
        ],
    ],
    resize_keyboard=True
)
# Submenus for Pump/Dump alerts and Settings
pump_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏱️ Timeframe"), KeyboardButton(text="📊 Price change")],
        [KeyboardButton(text="📡 Signals per day")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True
)

dump_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏱️ Timeframe"), KeyboardButton(text="📊 Price change")],
        [KeyboardButton(text="📡 Signals per day")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True
)

settings_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💡 Type Alerts")],
        [KeyboardButton(text="🟡 Binance ON/OFF"), KeyboardButton(text="🔵 Bybit ON/OFF")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True
)

# Инициализация базы данных
init_db()

@dp.message(Command("start"))
async def cmd_start(message: Message):
    username = message.from_user.username or str(message.from_user.id)
    if check_subscription(username):
        await message.answer(
            "Welcome back! 🎉 Your subscription is active. Use the menu to configure alerts.",
            reply_markup=main_menu_kb
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
        await message.answer(
            "Your key has been activated successfully! ✅\nUse the menu below to configure your alerts.",
            reply_markup=main_menu_kb
        )
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

@dp.message()
async def handle_menu(message: Message):
    # Переход в подменю Pump Alerts
    if message.text == "📈 Pump Alerts":
        await message.answer("Pump alerts settings. Choose an option:", reply_markup=pump_menu_kb)
    # Переход в подменю Dump Alerts
    elif message.text == "📉 Dump Alerts":
        await message.answer("Dump alerts settings. Choose an option:", reply_markup=dump_menu_kb)
    # Переход в общий раздел Settings
    elif message.text == "⚙️ Settings":
        await message.answer("General settings. Choose an option:", reply_markup=settings_menu_kb)
    # Возврат в главное меню
    elif message.text == "🔙 Back":
        await message.answer("Main menu:", reply_markup=main_menu_kb)


async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


