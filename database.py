import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta  # понадобится пакет python-dateutil
from config import ADMIN_ACCESS_KEY

DB_PATH = "keys.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # user_settings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            username TEXT PRIMARY KEY,
            exchange_binance INTEGER DEFAULT 1,
            exchange_bybit INTEGER DEFAULT 1,
            type_pump INTEGER DEFAULT 1,
            type_dump INTEGER DEFAULT 1,
            timeframe TEXT DEFAULT '15m',
            percent_change REAL DEFAULT 1.0,
            signals_per_day INTEGER DEFAULT 5,
            signals_sent_today INTEGER DEFAULT 0,
            last_reset DATETIME,
            is_admin INTEGER DEFAULT 0
        )
    """)
    # добавьте создание таблицы access_keys
    c.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            access_key TEXT UNIQUE NOT NULL,
            duration_months INTEGER NOT NULL,
            username TEXT,
            activated_at DATETIME,
            expires_at DATETIME,
            is_active INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

def add_key(access_key: str, duration_months: int):
    """Функция для предварительной загрузки ключей в базу (делаете это сами отдельно)."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO access_keys (access_key, duration_months, is_active) VALUES (?, ?, 0)",
        (access_key, duration_months),
    )
    conn.commit()
    conn.close()

def activate_key(access_key: str, username: str) -> bool:
    # сначала проверяем админский ключ
    if access_key == ADMIN_ACCESS_KEY:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # создаём или обновляем запись в user_settings для этого пользователя с is_admin=1
        c.execute("""
            INSERT INTO user_settings (username, is_admin)
            VALUES (?, 1)
            ON CONFLICT(username) DO UPDATE SET is_admin=1
        """, (username,))
        conn.commit()
        conn.close()
        return True

    # далее — прежняя логика активации для обычных ключей
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT duration_months, is_active, username FROM access_keys WHERE access_key = ?", (access_key,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    duration_months, is_active, existing_user = row
    if is_active == 1:
        conn.close()
        return existing_user == username
    # активируем: считаем expires_at и привязываем к username
    now = datetime.utcnow()
    expires_at = now + relativedelta(months=duration_months)
    c.execute(
        "UPDATE access_keys SET username=?, activated_at=?, expires_at=?, is_active=1 WHERE access_key=?",
        (username, now, expires_at, access_key),
    )
    conn.commit()
    conn.close()
    return True

def check_subscription(username: str) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # если пользователь — админ, пропускаем дальнейшие проверки
    c.execute("SELECT is_admin FROM user_settings WHERE username=?", (username,))
    user = c.fetchone()
    if user and user[0] == 1:
        conn.close()
        return True

    # ... прежняя логика проверки срока действия обычного ключа ...
    c.execute("SELECT expires_at FROM access_keys WHERE username=? AND is_active=1", (username,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    expires_at_str = row[0]
    expires_at = datetime.fromisoformat(expires_at_str)
    if datetime.utcnow() >= expires_at:
        c.execute("UPDATE access_keys SET is_active=0 WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return False
    conn.close()
    return True
