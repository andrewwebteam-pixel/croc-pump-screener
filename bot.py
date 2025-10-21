import asyncio
from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import Command

from config import TELEGRAM_TOKEN
from database import init_db, activate_key, check_subscription, update_user_setting, get_user_settings
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

# Храним текущий раздел и настройку для каждого пользователя
user_states = {}

# Варианты выбора для таймфрейма
timeframe_options = ["1m", "5m", "15m", "30m", "1h"]
timeframe_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in timeframe_options],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True
)

# Варианты для минимального процента изменения
price_options = ["0.5%", "1%", "2%", "5%", "10%", "20%", "50%"]
price_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=opt) for opt in price_options[:3]],
        [KeyboardButton(text=opt) for opt in price_options[3:]],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True
)

# Варианты для количества сигналов в день (1–20)
signals_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text=str(i)) for i in range(1, 6)],
        [KeyboardButton(text=str(i)) for i in range(6, 11)],
        [KeyboardButton(text=str(i)) for i in range(11, 16)],
        [KeyboardButton(text=str(i)) for i in range(16, 21)],
        [KeyboardButton(text="🔙 Back")],
    ],
    resize_keyboard=True
)
# Клавиатура для подменю включения Pump/Dump
type_alerts_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Pump ON/OFF"), KeyboardButton(text="Dump ON/OFF")],
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
    username = message.from_user.username or str(message.from_user.id)
    text = message.text.strip()

    # Если пользователь сейчас выбирает конкретное значение (таймфрейм, процент, сигналы)
    state = user_states.get(username, {})
    if 'setting' in state:
        # Выбор таймфрейма
        if state['setting'] == 'timeframe' and text in timeframe_options:
            update_user_setting(username, 'timeframe', text)
            state.pop('setting', None)
            if state.get('menu') == 'pump':
                await message.answer("Timeframe updated for Pump Alerts.", reply_markup=pump_menu_kb)
            else:
                await message.answer("Timeframe updated for Dump Alerts.", reply_markup=dump_menu_kb)
            return
        # Выбор процента изменения
        if state['setting'] == 'percent_change' and text in price_options:
            value = float(text.strip('%'))  # '5%' -> 5.0
            update_user_setting(username, 'percent_change', value)
            state.pop('setting', None)
            if state.get('menu') == 'pump':
                await message.answer("Percent change updated for Pump Alerts.", reply_markup=pump_menu_kb)
            else:
                await message.answer("Percent change updated for Dump Alerts.", reply_markup=dump_menu_kb)
            return
        # Выбор количества сигналов в день
        if state['setting'] == 'signals_per_day' and text.isdigit():
            update_user_setting(username, 'signals_per_day', int(text))
            state.pop('setting', None)
            if state.get('menu') == 'pump':
                await message.answer("Signals per day updated for Pump Alerts.", reply_markup=pump_menu_kb)
            else:
                await message.answer("Signals per day updated for Dump Alerts.", reply_markup=dump_menu_kb)
            return
        # Если пользователь нажал "Back" во время выбора значения
        if text == "🔙 Back":
            state.pop('setting', None)
            if state.get('menu') == 'pump':
                await message.answer("Back to Pump Alerts menu.", reply_markup=pump_menu_kb)
            else:
                await message.answer("Back to Dump Alerts menu.", reply_markup=dump_menu_kb)
            return

    # Пользователь выбирает раздел в главном меню или подменю
    if text == "📈 Pump Alerts":
        user_states[username] = {'menu': 'pump'}
        await message.answer("Pump alerts settings. Choose an option:", reply_markup=pump_menu_kb)
    elif text == "📉 Dump Alerts":
        user_states[username] = {'menu': 'dump'}
        await message.answer("Dump alerts settings. Choose an option:", reply_markup=dump_menu_kb)
    elif text == "💡 Type Alerts":
    # переход в подменю Type Alerts
        user_states[username]['menu'] = 'type_alerts'
        await message.answer("Select which alerts to enable/disable:", reply_markup=type_alerts_kb)
    elif text == "⚙️ Settings":
        user_states[username] = {'menu': 'settings'}
        await message.answer("General settings. Choose an option:", reply_markup=settings_menu_kb)
    elif text == "⏱️ Timeframe":
    # Запоминаем, что сейчас выбираем таймфрейм
        if 'menu' in user_states.get(username, {}):
            user_states[username]['setting'] = 'timeframe'
            await message.answer("Select timeframe:", reply_markup=timeframe_kb)
    elif text == "📊 Price change":
        if 'menu' in user_states.get(username, {}):
            user_states[username]['setting'] = 'percent_change'
            await message.answer("Select minimum percent change:", reply_markup=price_kb)
    elif text == "📡 Signals per day":
        if 'menu' in user_states.get(username, {}):
            user_states[username]['setting'] = 'signals_per_day'
            await message.answer("Select the number of signals per day:", reply_markup=signals_kb)
    # Toggle Pump ON/OFF
    elif text == "Pump ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["type_pump"] == 1 else 1
        update_user_setting(username, 'type_pump', new_val)
        status = "ON" if new_val else "OFF"
        await message.answer(f"Pump alerts are now {status}.", reply_markup=type_alerts_kb)
    # Toggle Dump ON/OFF
    elif text == "Dump ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["type_dump"] == 1 else 1
        update_user_setting(username, 'type_dump', new_val)
        status = "ON" if new_val else "OFF"
        await message.answer(f"Dump alerts are now {status}.", reply_markup=type_alerts_kb)
    # Toggle Binance ON/OFF
    elif text == "🟡 Binance ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["exchange_binance"] == 1 else 1
        update_user_setting(username, 'exchange_binance', new_val)
        status = "ON" if new_val else "OFF"
        await message.answer(f"Binance alerts are now {status}.", reply_markup=settings_menu_kb)
    # Toggle Bybit ON/OFF
    elif text == "🔵 Bybit ON/OFF":
        settings = get_user_settings(username)
        new_val = 0 if settings["exchange_bybit"] == 1 else 1
        update_user_setting(username, 'exchange_bybit', new_val)
        status = "ON" if new_val else "OFF"
        await message.answer(f"Bybit alerts are now {status}.", reply_markup=settings_menu_kb)
    elif text == "🔙 Back":
    # Возврат из подменю
    current_menu = user_states.get(username, {}).get('menu')
    if current_menu == 'type_alerts':
        user_states[username]['menu'] = 'settings'
        await message.answer("Back to Settings menu.", reply_markup=settings_menu_kb)
    elif current_menu == 'pump':
        await message.answer("Back to Pump Alerts menu.", reply_markup=pump_menu_kb)
    elif current_menu == 'dump':
        await message.answer("Back to Dump Alerts menu.", reply_markup=dump_menu_kb)
    else:
        await message.answer("Main menu:", reply_markup=main_menu_kb)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())


