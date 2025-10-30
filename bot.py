import asyncio
import logging
import sqlite3
import time
from typing import Callable

import aiohttp
from aiogram import Bot, Dispatcher
from aiogram.exceptions import TelegramBadRequest
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

# ---------------------------------------------------------------------------
# Logging configuration

logging.basicConfig(
    filename="pumpscreener.log",
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# ---------------------------------------------------------------------------
# Bot and dispatcher setup

# Initialize the bot and dispatcher. Ensure that the database tables exist
# before handling any messages.
bot = Bot(token=TELEGRAM_TOKEN)
dp = Dispatcher()

init_db()

# ---------------------------------------------------------------------------
# Keyboard definitions

# Main menu keyboard with options for pump/dump alerts, settings, profile info,
# and logout.
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="📈 Pump Alerts"),
            KeyboardButton(text="📉 Dump Alerts"),
        ],
        [
            KeyboardButton(text="⚙️ Settings"),
            KeyboardButton(text="👤 My Profile"),
        ],
        [KeyboardButton(text="🔓 Logout")],
    ],
    resize_keyboard=True,
)

# Pump alerts configuration keyboard
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

# Dump alerts configuration keyboard (mirrors pump menu)
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

# General settings keyboard
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

# Type of alerts configuration keyboard
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

# Tier menu keyboard (currently just a back button)
tier_menu_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text="🔙 Back")]],
    resize_keyboard=True,
)

# Timeframe selection keyboard
timeframe_options = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
timeframe_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in timeframe_options[:5]],
        [KeyboardButton(text=opt) for opt in timeframe_options[5:]],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True,
)

# Price change threshold keyboard
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

# Signals per day selection keyboard
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

# ---------------------------------------------------------------------------
# Global state and constants

# Per-user in-memory state for menu navigation, pending actions, and last menu
# message ID for message deletion.
user_states: dict[int, dict] = {}

# Default list of futures pairs monitored across both exchanges. This list is
# updated periodically based on trading volume via ``update_symbol_list``.
SYMBOLS: list[str] = [
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

# Timestamp of the last symbol list update. Measured in seconds since epoch.
TOP_SYMBOLS_LAST_UPDATE: float = 0.0

# ---------------------------------------------------------------------------
# Market data helpers


async def fetch_top_binance_symbols(limit: int = 30) -> list[str]:
    """Return the top Binance USDT‑margined futures pairs by 24h volume.

    Parameters
    ----------
    limit : int, optional
        Maximum number of symbols to return (default ``30``).

    Returns
    -------
    list[str]
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
    """Return the top Bybit USDT‑margined linear contracts by 24h volume.

    Parameters
    ----------
    limit : int, optional
        Maximum number of symbols to return (default ``30``).

    Returns
    -------
    list[str]
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
    """Update the global ``SYMBOLS`` list with top pairs from Binance and Bybit.

    This function refreshes the symbol list at most once per hour. It
    combines the top symbols from both exchanges, removes duplicates while
    preserving order, and logs the updated list. If an error occurs during
    retrieval, the existing list remains unchanged.
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

# ---------------------------------------------------------------------------
# Command handlers


@dp.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Handle the `/start` command.

    If the user has an active subscription, show the main menu. Otherwise
    prompt the user to enter their license key. The last bot message is
    tracked so it can be deleted when a new menu is shown.
    """
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    if check_subscription(user_id):
        response = await message.answer(
            "Welcome back! 🎉 Your subscription is active. Use the menu to configure alerts.",
            reply_markup=main_menu_kb,
        )
        # Record the ID of the last menu message
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        # Delete the command message to keep the chat clean
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
    else:
        user_states[user_id] = {"awaiting_key": True}
        response = await message.answer(
            "Hello! 👋 Please enter your license key to activate your subscription."
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return


@dp.message(Command("activate"))
async def cmd_activate(message: Message) -> None:
    """Handle the `/activate` command to manually activate a license key."""
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
    """Display a help message listing available commands."""
    await message.answer(
        "Here are the available commands 📋:\n"
        "/start — Start the bot and get activation instructions.\n"
        "/activate <key> — Activate your access key.\n"
        "/help — Show this help message."
    )

# ---------------------------------------------------------------------------
# Generic message handler


@dp.message()
async def handle_menu(message: Message) -> None:
    """Process all non-command text messages.

    This handler manages license key activation flow, menu navigation, and
    user preferences such as timeframe, price change threshold, and signal
    limits. It also deletes the previous menu message to keep the chat
    clean.
    """
    user_id = message.from_user.id
    username = message.from_user.username or str(user_id)
    text = message.text.strip()
    state = user_states.get(user_id, {})

    # Delete the previous bot message if present
    last_id = state.get("last_menu_msg_id")
    if last_id:
        try:
            await bot.delete_message(chat_id=user_id, message_id=last_id)
        except Exception:
            pass

    # Handle license key activation flow
    if state.get("awaiting_key"):
        if activate_key(text, username, user_id):
            user_states.pop(user_id, None)
            response = await message.answer(
                "Your key has been activated successfully! ✅\nUse the menu below to configure your alerts.",
                reply_markup=main_menu_kb,
            )
            user_states.setdefault(user_id, {})[
                "last_menu_msg_id"] = response.message_id
        else:
            response = await message.answer(
                "Invalid key or this key has already been used by another user. ❌"
            )
            user_states.setdefault(user_id, {})[
                "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return

    # Handle parameter selection within pump/dump menus
    if "setting" in state:
        setting = state["setting"]
        if setting == "timeframe" and text in timeframe_options:
            field_name = "timeframe_pump" if state.get(
                "menu") == "pump" else "timeframe_dump"
            update_user_setting(user_id, field_name, text)
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            response = await message.answer("Timeframe updated.", reply_markup=kb)
            user_states.setdefault(user_id, {})[
                "last_menu_msg_id"] = response.message_id
            try:
                await bot.delete_message(chat_id=user_id, message_id=message.message_id)
            except Exception:
                pass
            return
        if setting == "percent_change" and text in price_options:
            value = float(text.strip("%"))
            field_name = "percent_change_pump" if state.get(
                "menu") == "pump" else "percent_change_dump"
            update_user_setting(user_id, field_name, value)
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            response = await message.answer("Percent change updated.", reply_markup=kb)
            user_states.setdefault(user_id, {})[
                "last_menu_msg_id"] = response.message_id
            try:
                await bot.delete_message(chat_id=user_id, message_id=message.message_id)
            except Exception:
                pass
            return
        if setting == "signals_per_day" and text.isdigit():
            field_name = "signals_per_day_pump" if state.get(
                "menu") == "pump" else "signals_per_day_dump"
            update_user_setting(user_id, field_name, int(text))
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            response = await message.answer("Signals per day updated.", reply_markup=kb)
            user_states.setdefault(user_id, {})[
                "last_menu_msg_id"] = response.message_id
            try:
                await bot.delete_message(chat_id=user_id, message_id=message.message_id)
            except Exception:
                pass
            return
        if text == "🔙 Back":
            state.pop("setting", None)
            kb = pump_menu_kb if state.get("menu") == "pump" else dump_menu_kb
            response = await message.answer("Returning to menu.", reply_markup=kb)
            user_states.setdefault(user_id, {})[
                "last_menu_msg_id"] = response.message_id
            try:
                await bot.delete_message(chat_id=user_id, message_id=message.message_id)
            except Exception:
                pass
            return

    # Main menu navigation
    if text == "📈 Pump Alerts":
        user_states[user_id] = {"menu": "pump"}
        response = await message.answer(
            "Configure your Pump Alert settings below:", reply_markup=pump_menu_kb
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "📉 Dump Alerts":
        user_states[user_id] = {"menu": "dump"}
        response = await message.answer(
            "Configure your Dump Alert settings below:", reply_markup=dump_menu_kb
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "⚙️ Settings":
        response = await message.answer(
            "Configure your exchange and signal preferences:",
            reply_markup=settings_menu_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "💡 Type Alerts":
        user_states[user_id] = {"menu": "type_alerts"}
        response = await message.answer(
            "Configure which alert types you want to receive:",
            reply_markup=type_alerts_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "👤 My Profile":
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
            pump_status = "ON" if settings.get("type_pump", 1) else "OFF"
            dump_status = "ON" if settings.get("type_dump", 1) else "OFF"
            binance_status = "ON" if settings.get(
                "exchange_binance", 1) else "OFF"
            bybit_status = "ON" if settings.get("exchange_bybit", 1) else "OFF"
            signals_status = "ON" if settings.get(
                "signals_enabled", 1) else "OFF"
            timeframe_pump = settings.get(
                "timeframe_pump", settings.get("timeframe", "15m")
            )
            threshold_pump = settings.get(
                "percent_change_pump", settings.get("percent_change", 1.0)
            )
            signals_day_pump = settings.get(
                "signals_per_day_pump", settings.get("signals_per_day", 5)
            )
            timeframe_dump = settings.get(
                "timeframe_dump", settings.get("timeframe", "15m")
            )
            threshold_dump = settings.get(
                "percent_change_dump", settings.get("percent_change", 1.0)
            )
            signals_day_dump = settings.get(
                "signals_per_day_dump", settings.get("signals_per_day", 5)
            )
            tier_message = (
                "Your subscription details:\n"
                f"👤 Username: {settings.get('username', 'N/A')}\n"
                f"📅 Activated on: {activated_date}\n"
                f"⏳ Expires on: {expires_date}\n"
                "\n"
                "📈 Pump Alerts:\n"
                f"   🔔 Status: {pump_status}\n"
                f"   ⏱️ Timeframe: {timeframe_pump}\n"
                f"   🎯 Threshold: {threshold_pump}%\n"
                f"   🔔 Signals/day: {signals_day_pump}\n"
                "\n"
                "📉 Dump Alerts:\n"
                f"   🔔 Status: {dump_status}\n"
                f"   ⏱️ Timeframe: {timeframe_dump}\n"
                f"   🎯 Threshold: {threshold_dump}%\n"
                f"   🔔 Signals/day: {signals_day_dump}\n"
                "\n"
                f"🟡 Binance: {binance_status}\n"
                f"🔵 Bybit: {bybit_status}\n"
                f"📢 Signals: {signals_status}"
            )
            response = await message.answer(tier_message, reply_markup=main_menu_kb)
        else:
            response = await message.answer("No subscription found.", reply_markup=main_menu_kb)
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
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
        response = await message.answer(
            "You have been logged out. Send /start to log back in.",
            reply_markup=main_menu_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return

    # Pump/Dump submenu options
    if text == "⏱️ Timeframe":
        menu = user_states.get(user_id, {}).get("menu", "pump")
        user_states[user_id] = {"menu": menu, "setting": "timeframe"}
        response = await message.answer(
            "Select your preferred timeframe:", reply_markup=timeframe_kb
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "📊 Price change":
        menu = user_states.get(user_id, {}).get("menu", "pump")
        user_states[user_id] = {"menu": menu, "setting": "percent_change"}
        response = await message.answer(
            "Select price change threshold:", reply_markup=price_kb
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "📡 Signals per day":
        menu = user_states.get(user_id, {}).get("menu", "pump")
        user_states[user_id] = {"menu": menu, "setting": "signals_per_day"}
        response = await message.answer(
            "Select number of signals per day:", reply_markup=signals_kb
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "Pump ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("type_pump", 1) == 1 else 1
        update_user_setting(user_id, "type_pump", new_val)
        response = await message.answer(
            f"Pump alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=type_alerts_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "Dump ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("type_dump", 1) == 1 else 1
        update_user_setting(user_id, "type_dump", new_val)
        response = await message.answer(
            f"Dump alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=type_alerts_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "🟡 Binance ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("exchange_binance", 1) == 1 else 1
        update_user_setting(user_id, "exchange_binance", new_val)
        response = await message.answer(
            f"Binance alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "🔵 Bybit ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("exchange_bybit", 1) == 1 else 1
        update_user_setting(user_id, "exchange_bybit", new_val)
        response = await message.answer(
            f"Bybit alerts are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "🔔 Signals ON/OFF":
        settings = get_user_settings(user_id)
        new_val = 0 if settings.get("signals_enabled", 1) == 1 else 1
        update_user_setting(user_id, "signals_enabled", new_val)
        response = await message.answer(
            f"Signals are now {'ON' if new_val else 'OFF'}.",
            reply_markup=settings_menu_kb,
        )
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return
    if text == "🔙 Back":
        current_menu = user_states.get(user_id, {}).get("menu")
        if current_menu == "type_alerts":
            user_states[user_id] = {"menu": "settings"}
            response = await message.answer("Settings menu:", reply_markup=settings_menu_kb)
        elif current_menu in ("pump", "dump", "tier"):
            user_states.pop(user_id, None)
            response = await message.answer("Main menu:", reply_markup=main_menu_kb)
        else:
            response = await message.answer("Main menu:", reply_markup=main_menu_kb)
        user_states.setdefault(user_id, {})[
            "last_menu_msg_id"] = response.message_id
        try:
            await bot.delete_message(chat_id=user_id, message_id=message.message_id)
        except Exception:
            pass
        return

# ---------------------------------------------------------------------------
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
    counter_field: str,
) -> int:
    """Process pump or dump signals for a specific exchange and return updated count.

    This function iterates over the global ``SYMBOLS`` list, fetches price and volume
    change data for each symbol using the provided ``price_change_func``, and
    determines whether the price change exceeds the user-defined threshold. If a
    pump or dump condition is met (controlled by ``pump_on`` and ``dump_on``), a
    formatted signal is sent via the bot. The user's per-day signal counter,
    specified by ``counter_field``, is incremented and persisted via
    ``update_user_setting``. The updated ``signals_sent`` count is returned to
    facilitate successive calls that share state.

    Parameters
    ----------
    exchange_name : str
        Name of the exchange (e.g., "Binance" or "Bybit").
    user_id : int
        Telegram user ID to send messages to.
    timeframe : str
        Candle timeframe (e.g., "15m", "1h").
    threshold : float
        Percent change threshold to trigger alerts.
    pump_on : bool
        Whether pump alerts are enabled.
    dump_on : bool
        Whether dump alerts are enabled.
    signals_sent : int
        Number of signals already sent today for this user on this exchange.
    limit : int
        Maximum signals allowed per day for this user on this exchange.
    price_change_func : Callable[[str, str], asyncio.Future]
        Function to fetch price and volume change data for a given symbol and timeframe.
    counter_field : str
        Name of the user_settings field to update when a signal is sent (e.g.,
        ``"signals_sent_today_pump"`` or ``"signals_sent_today_dump"``).

    Returns
    -------
    int
        The updated number of signals sent today after processing all symbols.
    """
    for symbol in SYMBOLS:
        # Stop if the user has reached their daily limit for this category
        if signals_sent >= limit:
            break
        # Fetch price change data; skip on error
        try:
            data = await price_change_func(symbol, timeframe)
        except Exception as exc:
            logging.error("Error fetching data for %s on %s: %s",
                          symbol, exchange_name, exc)
            continue
        price_change = data.get("price_change", 0.0)
        volume_change = data.get("volume_change", 0.0)
        price_now = data.get("price_now", 0.0)
        # Compute RSI with fallback to free exchange API
        try:
            rsi_value = await get_rsi(symbol, timeframe)
        except Exception:
            rsi_value = None
        if rsi_value is None:
            rsi_value = await get_rsi_from_exchange(exchange_name, symbol, timeframe)
        # Fetch funding rate with fallback
        try:
            funding_rate = await get_funding_rate(exchange_name.lower(), symbol, "h1")
        except Exception:
            funding_rate = None
        if funding_rate is None:
            funding_rate = await get_funding_rate_free(exchange_name, symbol)
        # Fetch long/short ratio with fallback
        try:
            long_short_ratio = await get_long_short_ratio(symbol, time_type="h1")
        except Exception:
            long_short_ratio = None
        if long_short_ratio is None:
            long_short_ratio = await get_long_short_ratio_free(symbol, "1h")
        # Fetch open interest and order book ratio depending on exchange
        try:
            if exchange_name == "Binance":
                open_interest_val = await get_open_interest_binance(symbol)
                orderbook_ratio_val = await get_orderbook_ratio_binance(symbol)
            else:
                open_interest_val = await get_open_interest_bybit(symbol, timeframe)
                orderbook_ratio_val = await get_orderbook_ratio_bybit(symbol)
        except Exception as exc:
            logging.error(
                "Error fetching additional metrics for %s on %s: %s",
                symbol,
                exchange_name,
                exc,
            )
            open_interest_val = None
            orderbook_ratio_val = None
        # Determine whether to send a pump or dump alert
        should_send_pump = pump_on and price_change >= threshold
        should_send_dump = dump_on and price_change <= -threshold
        if should_send_pump or should_send_dump:
            message_text = format_signal(
                symbol=symbol,
                is_pump=should_send_pump,
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
            try:
                await bot.send_message(
                    chat_id=user_id,
                    text=message_text,
                    parse_mode="Markdown",
                )
            except TelegramBadRequest as exc:
                # If the chat is not found, stop processing for this user
                if "chat not found" in str(exc).lower():
                    logging.warning(
                        "Chat %s not found. Skipping user.", user_id)
                    return signals_sent
                # Otherwise log and stop to avoid spamming errors
                logging.error("Error sending message to %s: %s", user_id, exc)
                return signals_sent
            except Exception as exc:
                logging.error(
                    "Unexpected error sending message to %s: %s", user_id, exc)
                return signals_sent
            # Update counters and persist
            signals_sent += 1
            update_user_setting(user_id, counter_field, signals_sent)
    return signals_sent


async def check_signals() -> None:
    """Periodically evaluate signals for all users.

    Every five minutes, this coroutine updates the symbol list (no more than
    once per hour), iterates over users with active subscriptions, and
    triggers signal checks on Binance and Bybit according to each user's
    settings and daily limits. The function uses pump/dump specific
    thresholds and signal limits when available.
    """
    while True:
        await update_symbol_list()
        conn = sqlite3.connect("keys.db")
        c = conn.cursor()
        c.execute("SELECT username, user_id FROM user_settings")
        users = c.fetchall()
        conn.close()
        for username_db, user_id_db in users:
            # Skip entries with invalid user IDs
            if user_id_db is None or user_id_db == 0:
                continue
            # Skip users without an active subscription
            if not check_subscription(user_id_db):
                continue
            settings = get_user_settings(user_id_db)
            if not settings:
                continue
            # Retrieve per-category counters; default to zero if missing
            signals_sent_pump = settings.get("signals_sent_today_pump", 0)
            signals_sent_dump = settings.get("signals_sent_today_dump", 0)
            # If signals are globally disabled, skip this user entirely
            if settings.get("signals_enabled", 1) == 0:
                continue
            # Determine pump and dump parameters, falling back to common settings if category-specific fields are absent
            timeframe_pump = settings.get(
                "timeframe_pump", settings.get("timeframe", "15m"))
            threshold_pump = settings.get(
                "percent_change_pump", settings.get("percent_change", 1.0))
            signals_limit_pump = settings.get(
                "signals_per_day_pump", settings.get("signals_per_day", 5))
            timeframe_dump = settings.get(
                "timeframe_dump", settings.get("timeframe", "15m"))
            threshold_dump = settings.get(
                "percent_change_dump", settings.get("percent_change", 1.0))
            signals_limit_dump = settings.get(
                "signals_per_day_dump", settings.get("signals_per_day", 5))
            # Flags controlling whether each alert type is enabled
            pump_on = bool(settings.get("type_pump", 1))
            dump_on = bool(settings.get("type_dump", 1))
            binance_on = bool(settings.get("exchange_binance", 1))
            bybit_on = bool(settings.get("exchange_bybit", 1))
            # Process pump signals if enabled
            if pump_on:
                # Binance pump signals
                if binance_on and signals_sent_pump < signals_limit_pump:
                    signals_sent_pump = await process_exchange(
                        "Binance",
                        user_id_db,
                        timeframe_pump,
                        threshold_pump,
                        True,
                        False,
                        signals_sent_pump,
                        signals_limit_pump,
                        binance_price_change,
                        counter_field="signals_sent_today_pump",
                    )
                # Bybit pump signals
                if bybit_on and signals_sent_pump < signals_limit_pump:
                    signals_sent_pump = await process_exchange(
                        "Bybit",
                        user_id_db,
                        timeframe_pump,
                        threshold_pump,
                        True,
                        False,
                        signals_sent_pump,
                        signals_limit_pump,
                        bybit_price_change,
                        counter_field="signals_sent_today_pump",
                    )
            # Process dump signals if enabled
            if dump_on:
                # Binance dump signals
                if binance_on and signals_sent_dump < signals_limit_dump:
                    signals_sent_dump = await process_exchange(
                        "Binance",
                        user_id_db,
                        timeframe_dump,
                        threshold_dump,
                        False,
                        True,
                        signals_sent_dump,
                        signals_limit_dump,
                        binance_price_change,
                        counter_field="signals_sent_today_dump",
                    )
                # Bybit dump signals
                if bybit_on and signals_sent_dump < signals_limit_dump:
                    signals_sent_dump = await process_exchange(
                        "Bybit",
                        user_id_db,
                        timeframe_dump,
                        threshold_dump,
                        False,
                        True,
                        signals_sent_dump,
                        signals_limit_dump,
                        bybit_price_change,
                        counter_field="signals_sent_today_dump",
                    )
        await asyncio.sleep(300)

# ---------------------------------------------------------------------------
# Main entry point


async def main() -> None:
    """Entrypoint for running the bot.

    This function launches the background task for periodic signal checks and
    begins polling Telegram for new messages and commands.
    """
    asyncio.create_task(check_signals())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
