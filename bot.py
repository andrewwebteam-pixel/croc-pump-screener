import asyncio
import datetime
import logging
import sqlite3
import time
from typing import Callable, Optional

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup

from config import PROXY_URL, TELEGRAM_TOKEN
from database import (
    activate_key,
    check_subscription,
    get_user_settings,
    init_db,
    update_user_setting,
)
from utils.binance_api import get_price_change as binance_price_change
from utils.bybit_api import get_price_change as bybit_price_change
from utils.coinglass_api import get_funding_rate, get_long_short_ratio, get_rsi
from utils.free_metrics import (
    get_funding_rate_free,
    get_long_short_ratio_free,
    get_rsi_from_exchange,
)
from utils.formatters import format_signal
from utils.market_metrics import (
    get_open_interest_binance,
    get_open_interest_bybit,
    get_orderbook_ratio_binance,
    get_orderbook_ratio_bybit,
)
# ----------------------------------------------------------------------------
# Logging configuration

logging.basicConfig(
    filename="pumpscreener.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ----------------------------------------------------------------------------
# Bot and dispatcher setup

bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

init_db()  # Ensure the database is initialized on module import

# ----------------------------------------------------------------------------
# Keyboard definitions

main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📈 Pump Alerts"),
            KeyboardButton(text="📉 Dump Alerts"),
        ],
        [
            KeyboardButton(text="⚙️ Settings"),
            KeyboardButton(text="🎟️ My Tier"),
        ],
        [KeyboardButton(text="🔓 Logout")],
    ],
    resize_keyboard=True,
)

pump_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="⏱️ Timeframe"),
            KeyboardButton(text="📊 Price change"),
        ],
        [KeyboardButton(text="📡 Signals per day")],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

dump_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="⏱️ Timeframe"),
            KeyboardButton(text="📊 Price change"),
        ],
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
        [
            KeyboardButton(text="Pump ON/OFF"),
            KeyboardButton(text="Dump ON/OFF"),
        ],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

tier_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 Back")]],
    resize_keyboard=True,
)

timeframe_options = [
    "1m",
    "5m",
    "15m",
    "30m",
    "1h",
    "4h",
    "1d",
    "1w",
    "1M",
]
timeframe_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in timeframe_options[:5]],
        [KeyboardButton(text=opt) for opt in timeframe_options[5:]],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

price_options = [
    "0.1%",
    "0.2%",
    "0.3%",
    "0.4%",
    "0.5%",
    "1%",
    "2%",
    "5%",
    "10%",
    "20%",
    "50%",
]
price_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in price_options[:5]],
        [KeyboardButton(text=opt) for opt in price_options[5:]],
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

# ----------------------------------------------------------------------------
# Global state and constants

user_states: dict[int, dict] = {}

SYMBOLS = [
    "AAVEUSDT",
    "ADAUSDT",
    "ALGOUSDT",
    "APEUSDT",
    "APTUSDT",
    "ARBUSDT",
    "ATOMUSDT",
    "AVAXUSDT",
    "BANDUSDT",
    "BCHUSDT",
    "BNBUSDT",
    "BTCUSDT",
    "COMPUSDT",
    "CRVUSDT",
    "DOGEUSDT",
    "DOTUSDT",
    "DYDXUSDT",
    "EGLDUSDT",
    "ETCUSDT",
    "ETHUSDT",
    "FILUSDT",
    "GALAUSDT",
    "GMTUSDT",
    "GRTUSDT",
    "HBARUSDT",
    "ICPUSDT",
    "INJUSDT",
    "KAVAUSDT",
    "LDOUSDT",
    "LINKUSDT",
    "LTCUSDT",
    "MANAUSDT",
    "NEARUSDT",
    "OPUSDT",
    "SANDUSDT",
    "SNXUSDT",
    "SOLUSDT",
    "SUIUSDT",
    "TIAUSDT",
    "TONUSDT",
    "TRXUSDT",
    "UNIUSDT",
    "XLMUSDT",
    "XRPUSDT",
    "ZILUSDT",
]

TOP_SYMBOLS_LAST_UPDATE: float = 0.0

# ----------------------------------------------------------------------------
# Market data helpers


async def fetch_top_binance_symbols(limit: int = 30) -> list[str]:
    """
    Return the top Binance USDT-margined futures pairs by 24h volume.

    Args:
        limit: Maximum number of symbols to return.

    Returns:
        A list of symbol strings sorted by descending 24h quote volume.
    """
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, proxy=PROXY_URL, timeout=10) as resp:
            data = await resp.json()
    usdt_pairs = [item for item in data if item["symbol"].endswith("USDT")]
    sorted_pairs = sorted(
        usdt_pairs,
        key=lambda item: float(item["quoteVolume"]),
        reverse=True,
    )
    return [item["symbol"] for item in sorted_pairs[:limit]]


async def fetch_top_bybit_symbols(limit: int = 30) -> list[str]:
    """
    Return the top Bybit USDT-margined linear contracts by 24h volume.

    Args:
        limit: Maximum number of symbols to return.

    Returns:
        A list of symbol strings sorted by descending 24h turnover.
    """
    url = "https://api.bybit.com/v5/market/tickers"
    params = {"category": "linear"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL, timeout=10) as resp:
            data = await resp.json()
    tickers = data.get("result", {}).get("list", [])
    usdt_pairs = [item for item in tickers if item["symbol"].endswith("USDT")]
    sorted_pairs = sorted(
        usdt_pairs,
        key=lambda item: float(item["turnover24h"]),
        reverse=True,
    )
    return [item["symbol"] for item in sorted_pairs[:limit]]


async def update_symbol_list() -> None:
    """
    Update the global SYMBOLS list with top pairs from Binance and Bybit.

    This function refreshes the SYMBOLS list at most once per hour. It
    combines the top symbols from both exchanges, removes duplicates, and
    preserves order. If an error occurs, the existing list remains unchanged.
    """
    global SYMBOLS, TOP_SYMBOLS_LAST_UPDATE
    if time.time() - TOP_SYMBOLS_LAST_UPDATE < 3600:
        return
    try:
        binance_top = await fetch_top_binance_symbols()
        bybit_top = await fetch_top_bybit_symbols()
        unique_symbols: list[str] = []
        for sym in binance_top + bybit_top:
            if sym not in unique_symbols:
                unique_symbols.append(sym)
        SYMBOLS = unique_symbols
        TOP_SYMBOLS_LAST_UPDATE = time.time()
        logging.info("Updated SYMBOLS: %s", SYMBOLS)
    except Exception as exc:
        logging.error("Failed to update top symbols: %s", exc)

# ----------------------------------------------------------------------------
# Command handlers


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """
    Handle the /start command.

    If the user has an active subscription, the main menu is displayed. Otherwise
    the user is prompted to enter a license key.
    """
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    if check_subscription(user_id):
        await message.answer(
            "Welcome back! 🎉 Your subscription is active. Use the menu to configure alerts.",
            reply_markup=main_menu_kb,
        )
    else:
        user_states[user_id] = {"awaiting_key": True}
        await message.answer(
            "Hello! 👋 Please enter your license key to activate your subscription."
        )


@dp.message(Command("activate"))
async def cmd_activate(message: Message) -> None:
    """
    Handle the /activate command to manually activate a license key.
    """
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Usage: /activate <key> 🗝️")
        return
    access_key = parts[1]
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    if activate_key(access_key, username, user_id):
        await message.answer(
            "Your key has been activated successfully! ✅\nUse the menu below to configure your alerts.",
            reply_markup=main_menu_kb,
        )
    else:
        await message.answer(
            "Invalid key or this key has already been used by another user. ❌"
        )


@dp.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """
    Display a help message listing available commands.
    """
    await message.answer(
        "Here are the available commands 📋:\n"
        "/start — Start the bot and get activation instructions.\n"
        "/activate <key> — Activate your access key.\n"
        "/help — Show this help message."
    )

# ----------------------------------------------------------------------------
# Generic message handler


@dp.message()
async def handle_menu(message: Message) -> None:
    """
    Process all non-command text messages.

    This handler manages license key activation, menu navigation, and user
    preferences such as timeframe, price change threshold, and signals per day.
    """
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    text = message.text.strip()
    state = user_states.get(user_id, {})
    # License key activation flow
    if state.get("awaiting_key"):
        if activate_key(text, username, user_id):
            user_states.pop(user_id, None)
            await message.answer(
                "Your key has been activated successfully! ✅\nUse the menu below to configure your alerts.",
                reply_markup=main_menu_kb,
            )
        else:
            await message.answer(
                "Invalid key or this key has already been used by another user. ❌"
            )
        return
    # Parameter selection within pump/dump menus
    if "setting" in state:
        setting = state["setting"]
        if setting == "timeframe" and text in timeframe_options:
            update_user_setting(user_id, "timeframe", text)
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Timeframe updated.", reply_markup=kb)
            return
        if setting == "percent_change" and text in price_options:
            value = float(text.strip("%"))
            update_user_setting(user_id, "percent_change", value)
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Percent change updated.", reply_markup=kb)
            return
        if setting == "signals_per_day" and text.isdigit():
            update_user_setting(user_id, "signals_per_day", int(text))
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Signals per day updated.", reply_markup=kb)
            return
        if text == "🔙 Back":
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            await message.answer("Returning to menu.", reply_markup=kb)
            return
    # Main menu navigation
    if text == "📈 Pump Alerts":
        user_states[user_id] = {"menu": "pump"}
        await message.answer(
            "Configure your Pump Alert settings below:",
            reply_markup=pump_menu_kb,
        )
        return
    if text == "📉 Dump Alerts":
        user_states[user_id] = {"menu": "dump"}
        await message.answer(
            "Configure your Dump Alert settings below:",
            reply_markup=dump_menu_kb,
        )
        return
    if text == "⚙️ Settings":
        await message.answer(
            "Configure your exchange and signal preferences:",
            reply_markup=settings_menu_kb,
        )
        return
    if text == "💡 Type Alerts":
        user_states[user_id] = {"menu": "type_alerts"}
        await message.answer(
            "Configure which alert types you want to receive:",
            reply_markup=type_alerts_kb,
        )
        return
    if text == "🎟️ My Tier":
        settings = get_user_settings(user_id)
        if settings:
            conn = sqlite3.connect("keys.db")
            c = conn.cursor()
            c.execute(
                "SELECT activated_at, expires_at FROM access_keys WHERE user_id=? AND is_active=1",
                (user_id,),
            )
            dates = c.fetchone()
            conn.close()
            if dates:
                activated_at_str, expires_at_str = dates
                activated_date = activated_at_str.split(" ")[0]
                expires_date = expires_at_str.split(" ")[0]
            else:
                activated_date = "N/A"
                expires_date = "N/A"
            await message.answer(
                f"Your subscription details:\n"
                f"👤 Username: {settings.get('username', 'N/A')}\n"
                f"📅 Activated on: {activated_date}\n"
                f"⏳ Expires on: {expires_date}\n"
                f"⏱️ Timeframe: {settings.get('timeframe', '15m')}\n"
                f"🎯 Threshold: {settings.get('percent_change', 1.0)}%\n"
                f"🔔 Signals/day: {settings.get('signals_per_day', 5)}",
                reply_markup=main_menu_kb,
            )
        else:
            await message.answer("No subscription found.", reply_markup=main_menu_kb)
        return
    if text == "🔓 Logout":
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute(
            "SELECT username, is_admin FROM user_settings WHERE user_id=?",
            (user_id,),
        )
        row = c.fetchone()
        if row:
            username_db, is_admin = row
            if not is_admin:
                c.execute(
                    "UPDATE access_keys SET is_active=0, user_id=NULL WHERE username=?",
                    (username_db,),
                )
            c.execute("DELETE FROM user_settings WHERE user_id=?", (user_id,))
        conn.commit()
        conn.close()
        user_states.pop(user_id, None)
        await message.answer(
            "You have been logged out. Send /start to log back in.",
            reply_markup=main_menu_kb,
        )
        return
    # Pump/Dump submenu options
    if text == "⏱️ Timeframe":
        menu = user_states.get(user_id, {}).get("menu", "pump")
        user_states[user_id] = {"menu": menu, "setting": "timeframe"}
        await message.answer("Select your preferred timeframe:", reply_markup=timeframe_kb)
        return
    if text == "📊 Price change":
        menu = user_states.get(user_id, {}).get("menu", "pump")
        user_states[user_id] = {"menu": menu, "setting": "percent_change"}
        await message.answer("Select price change threshold:", reply_markup=price_kb)
        return
    if text == "📡 Signals per day":
        menu = user_states.get(user_id, {}).get("menu", "pump")
        user_states[user_id] = {"menu": menu, "setting": "signals_per_day"}
        await message.answer("Select number of signals per day:", reply_markup=signals_kb)
        return
    if text == "Pump ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("type_pump", 1) == 1 else 1
        update_user_setting(user_id, "type_pump", new_val)
        await message.answer(
            f"Pump alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=type_alerts_kb,
        )
        return
    if text == "Dump ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("type_dump", 1) == 1 else 1
        update_user_setting(user_id, "type_dump", new_val)
        await message.answer(
            f"Dump alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=type_alerts_kb,
        )
        return
    if text == "🟡 Binance ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("exchange_binance", 1) == 1 else 1
        update_user_setting(user_id, "exchange_binance", new_val)
        await message.answer(
            f"Binance alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )
        return
    if text == "🔵 Bybit ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("exchange_bybit", 1) == 1 else 1
        update_user_setting(user_id, "exchange_bybit", new_val)
        await message.answer(
            f"Bybit alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )
        return
    if text == "🔔 Signals ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("signals_enabled", 1) == 1 else 1
        update_user_setting(user_id, "signals_enabled", new_val)
        await message.answer(
            f"Signals are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )
        return
    if text == "🔙 Back":
        current_menu = user_states.get(user_id, {}).get("menu")
        if current_menu == "type_alerts":
            user_states[user_id] = {"menu": "settings"}
            await message.answer("Settings menu:", reply_markup=settings_menu_kb)
        elif current_menu in ("pump", "dump", "tier"):
            user_states.pop(user_id, None)
            await message.answer("Main menu:", reply_markup=main_menu_kb)
        else:
            await message.answer("Main menu:", reply_markup=main_menu_kb)
        return

# ----------------------------------------------------------------------------
# Signal processing helpers


async def process_exchange(
    exchange_name: str,
    user_id: int,
    timeframe: str,
    threshold: float,
    pump_on: bool,
    dump_on: bool,
    signals_sent: int,
    limit: int,
    price_change_func: Callable[[str, str], asyncio.Future],
) -> None:
    """
    Process pump/dump signals for a specific exchange and send alerts.

    Iterates over the SYMBOLS list, retrieves price and volume change data, and
    checks whether the changes exceed user-defined thresholds. If a pump or
    dump condition is met, formats and sends a signal message via the bot.
    Additional indicators (RSI, funding rate, long/short ratio) are fetched
    with fallback strategies.
    """
    for symbol in SYMBOLS:
        if signals_sent >= limit:
            break
        try:
            data = await price_change_func(symbol, timeframe)
        except Exception as exc:
            logging.error("Error fetching data for %s on %s: %s",
                          symbol, exchange_name, exc)
            continue
        price_change = data.get("price_change", 0.0)
        volume_change = data.get("volume_change", 0.0)
        price_now = data.get("price_now", 0.0)
        try:
            rsi_value = await get_rsi(symbol, timeframe)
        except Exception:
            rsi_value = None
        if rsi_value is None:
            rsi_value = await get_rsi_from_exchange(exchange_name, symbol, timeframe)
        try:
            funding_rate = await get_funding_rate(exchange_name.lower(), symbol, "h1")
        except Exception:
            funding_rate = None
        if funding_rate is None:
            funding_rate = await get_funding_rate_free(exchange_name, symbol)
        try:
            long_short_ratio = await get_long_short_ratio(symbol, time_type="h1")
        except Exception:
            long_short_ratio = None
        if long_short_ratio is None:
            long_short_ratio = await get_long_short_ratio_free(symbol, "1h")
        try:
            if exchange_name == "Binance":
                open_interest_val = await get_open_interest_binance(symbol)
                orderbook_ratio_val = await get_orderbook_ratio_binance(symbol)
            else:
                open_interest_val = await get_open_interest_bybit(symbol)
                orderbook_ratio_val = await get_orderbook_ratio_bybit(symbol)
        except Exception as e:
            logging.error(
                f"Error fetching additional metrics for {symbol} on {exchange_name}: {e}"
            )
            open_interest_val = None
            orderbook_ratio_val = None

        if pump_on and price_change >= threshold:
            message_text = format_signal(
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
                open_interest=open_interest_val,
                orderbook_ratio=orderbook_ratio_val,
            )
            await bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")
            signals_sent += 1
            update_user_setting(user_id, "signals_sent_today", signals_sent)
        elif dump_on and price_change <= -threshold:
            message_text = format_signal(
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
                open_interest=open_interest_val,
                orderbook_ratio=orderbook_ratio_val,
            )
            await bot.send_message(chat_id=user_id, text=message_text, parse_mode="Markdown")
            signals_sent += 1
            update_user_setting(user_id, "signals_sent_today", signals_sent)


async def check_signals() -> None:
    """
    Periodically evaluate signals for all users.

    Runs indefinitely in the background. Every five minutes, updates the symbol
    list (at most once per hour), iterates over users with active
    subscriptions, and triggers signal checks on Binance and Bybit according
    to each user's settings and daily limits.
    """
    while True:
        await update_symbol_list()
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute("SELECT username, user_id FROM user_settings")
        users = c.fetchall()
        conn.close()
        for username_db, user_id_db in users:
            if user_id_db is None or user_id_db == 0:
                continue
            if not check_subscription(user_id_db):
                continue
            settings = get_user_settings(user_id_db)
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
                    user_id_db,
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
                    user_id_db,
                    timeframe,
                    threshold,
                    pump_on,
                    dump_on,
                    signals_sent,
                    limit,
                    bybit_price_change,
                )
        await asyncio.sleep(300)

# ----------------------------------------------------------------------------
# Main entry point


async def main() -> None:
    """
    Entrypoint for running the bot.

    Spawns the background task for periodic signal checks and starts polling
    Telegram for new messages and commands.
    """
    asyncio.create_task(check_signals())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
