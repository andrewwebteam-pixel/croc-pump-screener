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
from utils.coinglass_api import get_rsi, get_funding_rate, get_long_short_ratio
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
        [
            KeyboardButton(text="🟡 Binance ON/OFF"),
            KeyboardButton(text="🔵 Bybit ON/OFF"),
        ],
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
SYMBOLS = ["BTCUSDT", "ETHUSDT"]

# --- Команды ---


@dp.message(Command("start"))
async def cmd_start(message: Message):
    username = message.from_user.username or str(message.from_user.id)
    if check_subscription(username) and not user_states.get(username, {}).get("awaiting_key"):
        await message.answer(
            "Welcome back! 🎉 Your subscription is active. Use the menu to configure alerts.",
            reply_markup=main_menu_kb,
        )
    else:
        user_states[username] = {"awaiting_key": True}
        await message.answer(
            "Hello! 👋 Please enter your license key to activate your subscription."
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
            reply_markup=main_menu_kb,
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

# --- Обработка меню ---


@dp.message()
async def handle_menu(message: Message):
    username = message.from_user.username or str(message.from_user.id)
    text = message.text.strip()
    state = user_states.get(username, {})

    # Активация ключа
    if state.get("awaiting_key"):
        if activate_key(text, username):
            user_states.pop(username, None)
            await message.answer(
                "Your key has been activated successfully! ✅\nUse the menu below to configure your alerts.",
                reply_markup=main_menu_kb,
            )
        else:
            await message.answer(
                "Invalid key or this key has already been used by another user. ❌"
            )
        return

    # --- Выбор параметров ---
    if "setting" in state:
        if state["setting"] == "timeframe" and text in timeframe_options:
            update_user_setting(username, "timeframe", text)
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Timeframe updated.", reply_markup=kb)
            return

        if state["setting"] == "percent_change" and text in price_options:
            value = float(text.strip("%"))
            update_user_setting(username, "percent_change", value)
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Percent change updated.", reply_markup=kb)
            return

        if state["setting"] == "signals_per_day" and text.isdigit():
            update_user_setting(username, "signals_per_day", int(text))
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Signals per day updated.", reply_markup=kb)
            return

        if text == "🔙 Back":
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Back to menu.", reply_markup=kb)
            return

    # --- Главное меню ---
    if text == "📈 Pump Alerts":
        user_states[username] = {"menu": "pump"}
        await message.answer("Pump alerts settings:", reply_markup=pump_menu_kb)

    elif text == "📉 Dump Alerts":
        user_states[username] = {"menu": "dump"}
        await message.answer("Dump alerts settings:", reply_markup=dump_menu_kb)

    elif text == "⚙️ Settings":
        user_states[username] = {"menu": "settings"}
        await message.answer("General settings:", reply_markup=settings_menu_kb)

    elif text == "🎟️ My Tier":
        user_states[username] = {"menu": "tier"}
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute(
            "SELECT duration_months, activated_at, expires_at "
            "FROM access_keys WHERE username=? AND is_active=1",
            (username,),
        )
        key_data = c.fetchone()
        conn.close()

        if key_data:
            duration_months, activated_at, expires_at = key_data
            plan = f"{duration_months} month(s)"
            start_date = activated_at or "—"
            end_date = expires_at or "—"
            await message.answer(
                f"🧾 Plan: {plan}\nStart date: {start_date}\nEnd date: {end_date}",
                reply_markup=tier_menu_kb,
            )
        else:
            await message.answer("No active subscription found.", reply_markup=tier_menu_kb)

    elif text == "🔓 Logout":
        user_states[username] = {"awaiting_key": True}
        await message.answer(
            "You have been logged out. Please enter your license key to activate your subscription again.",
            reply_markup=None,
        )

    elif text == "💡 Type Alerts":
        user_states[username]["menu"] = "type_alerts"
        await message.answer(
            "Select which alerts to enable/disable:", reply_markup=type_alerts_kb
        )

    elif text == "⏱️ Timeframe":
        user_states[username]["setting"] = "timeframe"
        await message.answer("Select timeframe:", reply_markup=timeframe_kb)

    elif text == "📊 Price change":
        user_states[username]["setting"] = "percent_change"
        await message.answer("Select minimum percent change:", reply_markup=price_kb)

    elif text == "📡 Signals per day":
        user_states[username]["setting"] = "signals_per_day"
        await message.answer("Select number of signals per day:", reply_markup=signals_kb)

    elif text == "Pump ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["type_pump"] == 1 else 1
        update_user_setting(username, "type_pump", new_val)
        await message.answer(
            f"Pump alerts are now {'ON' if new_val else 'OFF'}.", reply_markup=type_alerts_kb
        )

    elif text == "Dump ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["type_dump"] == 1 else 1
        update_user_setting(username, "type_dump", new_val)
        await message.answer(
            f"Dump alerts are now {'ON' if new_val else 'OFF'}.", reply_markup=type_alerts_kb
        )

    elif text == "🟡 Binance ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["exchange_binance"] == 1 else 1
        update_user_setting(username, "exchange_binance", new_val)
        await message.answer(
            f"Binance alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )

    elif text == "🔵 Bybit ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["exchange_bybit"] == 1 else 1
        update_user_setting(username, "exchange_bybit", new_val)
        await message.answer(
            f"Bybit alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )

    elif text == "🔔 Signals ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings.get("signals_enabled", 1) == 1 else 1
        update_user_setting(username, "signals_enabled", new_val)
        await message.answer(
            f"Signals are now {'ON' if new_val else 'OFF'}.", reply_markup=settings_menu_kb
        )

    elif text == "🔙 Back":
        current_menu = user_states.get(username, {}).get("menu")
        if current_menu == "type_alerts":
            user_states[username]["menu"] = "settings"
            await message.answer("Back to Settings menu.", reply_markup=settings_menu_kb)
        elif current_menu in ("pump", "dump", "tier"):
            user_states.pop(username, None)
            await message.answer("Main menu:", reply_markup=main_menu_kb)
        else:
            await message.answer("Main menu:", reply_markup=main_menu_kb)


# --- Логика сигналов ---


async def check_signals():
    while True:
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute("SELECT username FROM access_keys WHERE is_active=1")
        users = [row[0] for row in c.fetchall()]
        conn.close()

        for username in users:
            if not check_subscription(username):
                continue

            settings = get_user_settings(username)
            signals_sent = settings["signals_sent_today"] or 0
            limit = settings["signals_per_day"]

            if settings.get("signals_enabled", 1) == 0 or signals_sent >= limit:
                continue

            timeframe = settings["timeframe"]
            threshold = settings["percent_change"]
            pump_on = bool(settings["type_pump"])
            dump_on = bool(settings["type_dump"])
            binance_on = bool(settings["exchange_binance"])
            bybit_on = bool(settings["exchange_bybit"])

            if binance_on:
                await process_exchange(
                    "Binance",
                    username,
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
                    username,
                    timeframe,
                    threshold,
                    pump_on,
                    dump_on,
                    signals_sent,
                    limit,
                    bybit_price_change,
                )

        await asyncio.sleep(300)


async def process_exchange(
    exchange_name: str,
    username: str,
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

        price_change = data["price_change"]
        volume_change = data["volume_change"]
        price_now = data["price_now"]

        if pump_on and price_change >= threshold:
            message = format_signal(
                symbol=symbol,
                is_pump=True,
                exchange=exchange_name,
                price_now=price_now,
                price_change=price_change,
                volume_now=data["volume_now"],
                volume_change=volume_change,
            )
            await bot.send_message(chat_id=username, text=message)
            signals_sent += 1
            update_user_setting(username, "signals_sent_today", signals_sent)

        elif dump_on and price_change <= -threshold:
            message = format_signal(
                symbol=symbol,
                is_pump=False,
                exchange=exchange_name,
                price_now=price_now,
                price_change=price_change,
                volume_now=data["volume_now"],
                volume_change=volume_change,
            )
            await bot.send_message(chat_id=username, text=message)
            signals_sent += 1
            update_user_setting(username, "signals_sent_today", signals_sent)


# --- Основной запуск ---


async def main():
    asyncio.create_task(check_signals())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
