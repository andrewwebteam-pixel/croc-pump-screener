import asyncio
import logging
import sqlite3

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from config import TELEGRAM_TOKEN
from database import (
    init_db,
    activate_key,
    check_subscription,
    update_user_setting,
    get_user_settings,
)
from utils.coinglass_api import (
    get_rsi,
    get_funding_rate,
    get_long_short_ratio,
)
from utils.free_metrics import (
    get_funding_rate_free,
    get_long_short_ratio_free,
    get_rsi_from_exchange,
)
from utils.binance_api import get_price_change as binance_price_change
from utils.bybit_api import get_price_change as bybit_price_change
from utils.formatters import format_signal

# Настройка логирования
logging.basicConfig(
    filename="pumpscreener.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

# Инициализация базы данных
init_db()

# --- Клавиатуры ---
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📈 Pump Alerts"), KeyboardButton(text="📉 Dump Alerts")],
        [KeyboardButton(text="⚙️ Settings"), KeyboardButton(text="🎟️ My Tier")],
        [KeyboardButton(text="🔓 Logout")],
    ],
    resize_keyboard=True,
)

pump_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏱️ Timeframe"), KeyboardButton(text="📊 Price change")],
        [KeyboardButton(text="📡 Signals per day")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

dump_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="⏱️ Timeframe"), KeyboardButton(text="📊 Price change")],
        [KeyboardButton(text="📡 Signals per day")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

settings_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="💡 Type Alerts")],
        [KeyboardButton(text="🟡 Binance ON/OFF"), KeyboardButton(text="🔵 Bybit ON/OFF")],
        [KeyboardButton(text="🔔 Signals ON/OFF")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

type_alerts_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Pump ON/OFF"), KeyboardButton(text="Dump ON/OFF")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

tier_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 Back")]],
    resize_keyboard=True,
)

timeframe_options = ["1m", "5m", "15m", "30m", "1h"]
timeframe_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in timeframe_options],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

price_options = ["0.5%", "1%", "2%", "5%", "10%", "20%", "50%"]
price_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in price_options[:3]],
        [KeyboardButton(text=opt) for opt in price_options[3:]],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

signals_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=str(i)) for i in range(1, 6)],
        [KeyboardButton(text=str(i)) for i in range(6, 11)],
        [KeyboardButton(text=str(i)) for i in range(11, 16)],
        [KeyboardButton(text=str(i)) for i in range(16, 21)],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

# --- Глобальные переменные ---
user_states = {}
SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

# --- Команды ---


@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    if check_subscription(user_id):
        await message.answer(
            "Welcome back! 🎉 Your subscription is active. Use the menu to configure alerts.",
            reply_markup=main_menu_kb,
        )
    else:
        user_states[user_id] = {"awaiting_key": True}
        await message.answer("Hello! 👋 Please enter your license key to activate your subscription.")


@dp.message(Command("activate"))
async def cmd_activate(message: Message):
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Usage: /activate <key> 🗝️")
        return

    access_key = parts[1]
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)

    if activate_key(access_key, username):
        await message.answer(
            "Your key has been activated successfully! ✅\nUse the menu below to configure your alerts.",
            reply_markup=main_menu_kb,
        )
    else:
        await message.answer("Invalid key or this key has already been used by another user. ❌")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(
        "Here are the available commands 📋:\n"
        "/start — Start the bot and get activation instructions.\n"
        "/activate <key> — Activate your access key.\n"
        "/help — Show this help message."
    )

# --- Основная логика сигналов ---


async def process_exchange(
    exchange_name: str,
    user_id: int,
    timeframe: str,
    threshold: float,
    pump_on: bool,
    dump_on: bool,
    signals_sent: int,
    limit: int,
    price_change_func,
):
    for symbol in SYMBOLS:
        if signals_sent >= limit:
            break

        try:
            data = await price_change_func(symbol, timeframe)
        except Exception as e:
            logging.error(f"Error fetching data for {symbol} on {exchange_name}: {e}")
            continue

        price_change = data.get("price_change", 0)
        volume_change = data.get("volume_change", 0)
        price_now = data.get("price_now", 0)

        # Метрики с fallback на бесплатные API
        try:
            rsi_value = await get_rsi(symbol, timeframe)
        except Exception:
            rsi_value = await get_rsi_from_exchange(exchange_name, symbol, timeframe)

        try:
            funding_rate = await get_funding_rate(exchange_name, symbol, "h1")
        except Exception:
            funding_rate = await get_funding_rate_free(exchange_name, symbol)

        try:
            long_short_ratio = await get_long_short_ratio(symbol, time_type="h1")
        except Exception:
            long_short_ratio = await get_long_short_ratio_free(symbol, "1h")

        if pump_on and price_change >= threshold:
            message = format_signal(
                symbol=symbol,
                is_pump=True,
                exchange=exchange_name,
                price_now=price_now,
                price_change=price_change,
                volume_now=data.get("volume_now"),
                volume_change=volume_change,
                rsi=rsi_value,
                funding=funding_rate,
                long_short_ratio=long_short_ratio,
            )
            await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
            signals_sent += 1
            update_user_setting(user_id, "signals_sent_today", signals_sent)

        elif dump_on and price_change <= -threshold:
            message = format_signal(
                symbol=symbol,
                is_pump=False,
                exchange=exchange_name,
                price_now=price_now,
                price_change=price_change,
                volume_now=data.get("volume_now"),
                volume_change=volume_change,
                rsi=rsi_value,
                funding=funding_rate,
                long_short_ratio=long_short_ratio,
            )
            await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
            signals_sent += 1
            update_user_setting(user_id, "signals_sent_today", signals_sent)


async def check_signals():
    while True:
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute("SELECT username, user_id FROM access_keys WHERE is_active=1")
        users = [(row[0], row[1]) for row in c.fetchall()]
        conn.close()

        for username, user_id in users:
            if not check_subscription(user_id):
                continue

            settings = get_user_settings(user_id)
            if not settings:
                continue

            signals_sent = settings.get("signals_sent_today", 0)
            limit = settings.get("signals_per_day", 5)
            if settings.get("signals_enabled", 1) == 0 or signals_sent >= limit:
                continue

            timeframe = settings.get("timeframe", "15m")
            threshold = settings.get("percent_change", 1.0)
            pump_on = bool(settings.get("type_pump", 1))
            dump_on = bool(settings.get("type_dump", 1))
            binance_on = bool(settings.get("exchange_binance", 1))
            bybit_on = bool(settings.get("exchange_bybit", 1))

            if binance_on:
                await process_exchange(
                    "Binance",
                    user_id,
                    timeframe,
                    threshold,
                    pump_on,
                    dump_on,
                    signals_sent,
                    limit,
                    binance_price_change,
                )

            if bybit_on:
                await process_exchange(
                    "Bybit",
                    user_id,
                    timeframe,
                    threshold,
                    pump_on,
                    dump_on,
                    signals_sent,
                    limit,
                    bybit_price_change,
                )

        await asyncio.sleep(300)

# --- Основной запуск ---


async def main():
    asyncio.create_task(check_signals())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
