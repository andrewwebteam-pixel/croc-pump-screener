import sqlite3
from datetime import datetime
# понадобится пакет python-dateutil
from dateutil.relativedelta import relativedelta
from config import ADMIN_ACCESS_KEY

DB_PATH = "keys.db"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # user_settings table
    c.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            username TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            exchange_binance INTEGER DEFAULT 1,
            exchange_bybit INTEGER DEFAULT 1,
            type_pump INTEGER DEFAULT 1,
            type_dump INTEGER DEFAULT 1,
            timeframe TEXT DEFAULT '15m',
            percent_change REAL DEFAULT 1.0,
            signals_per_day INTEGER DEFAULT 5,
            signals_sent_today INTEGER DEFAULT 0,
            signals_enabled INTEGER DEFAULT 1,
            last_reset DATETIME,
            is_admin INTEGER DEFAULT 0
        )
    """)
    # Проверяем наличие нужных колонок и добавляем их при отсутствии
    c.execute("PRAGMA table_info(user_settings)")
    existing_columns = [row[1] for row in c.fetchall()]
    if 'signals_sent_today_pump' not in existing_columns:
        c.execute(
            "ALTER TABLE user_settings ADD COLUMN signals_sent_today_pump INTEGER DEFAULT 0")
    if 'signals_sent_today_dump' not in existing_columns:
        c.execute(
            "ALTER TABLE user_settings ADD COLUMN signals_sent_today_dump INTEGER DEFAULT 0")

    # добавьте создание таблицы access_keys
    c.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            access_key TEXT UNIQUE NOT NULL,
            duration_months INTEGER NOT NULL,
            username TEXT,
            user_id INTEGER,
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


def activate_key(access_key: str, username: str, user_id: int) -> bool:
    # сначала проверяем админский ключ
    if access_key == ADMIN_ACCESS_KEY:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        # создаём или обновляем запись в user_settings для этого пользователя с is_admin=1
        c.execute("""
            INSERT INTO user_settings (username, user_id, is_admin)
            VALUES (?, ?, 1)
            ON CONFLICT(username) DO UPDATE SET user_id=?, is_admin=1
        """, (username, user_id, user_id))
        conn.commit()
        conn.close()
        return True

    # далее — прежняя логика активации для обычных ключей
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "SELECT duration_months, is_active, username FROM access_keys WHERE access_key = ?", (access_key,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    duration_months, is_active, existing_user = row
    if is_active == 1:
        # Key already activated - allow re-activation by same user to update user_id
        if existing_user == username:
            # Update user_id for this existing activation (important for migration)
            c.execute(
                "UPDATE access_keys SET user_id=? WHERE access_key=?",
                (user_id, access_key)
            )
            # Also ensure user_settings has correct user_id
            c.execute(
                "UPDATE user_settings SET user_id=? WHERE username=?",
                (user_id, username)
            )
            conn.commit()
            conn.close()
            return True
        else:
            # Key activated by different user - reject
            conn.close()
            return False
    # активируем: считаем expires_at и привязываем к username и user_id
    now = datetime.utcnow()
    expires_at = now + relativedelta(months=duration_months)
    c.execute(
        "UPDATE access_keys SET username=?, user_id=?, activated_at=?, expires_at=?, is_active=1 WHERE access_key=?",
        (username, user_id, now, expires_at, access_key),
    )
    # Создаём запись в user_settings с user_id
    c.execute("""
        INSERT INTO user_settings (username, user_id)
        VALUES (?, ?)
        ON CONFLICT(username) DO UPDATE SET user_id=?
    """, (username, user_id, user_id))
    conn.commit()
    conn.close()
    return True


def check_subscription(user_id: int) -> bool:
    """
    Check if a user has an active subscription based on their numeric Telegram user_id.
    This is more reliable than using username which can change.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # Check if user is admin
    c.execute(
        "SELECT is_admin, username FROM user_settings WHERE user_id=?", (user_id,))
    user = c.fetchone()
    if user and user[0] == 1:
        conn.close()
        return True

    # If user not found in user_settings, they haven't activated yet
    if user is None:
        conn.close()
        return False

    username = user[1]  # Get username for access_keys lookup

    # Check expiration of regular key
    c.execute(
        "SELECT expires_at FROM access_keys WHERE username=? AND is_active=1", (username,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    expires_at_str = row[0]
    expires_at = datetime.fromisoformat(expires_at_str)
    if datetime.utcnow() >= expires_at:
        c.execute(
            "UPDATE access_keys SET is_active=0 WHERE username=?", (username,))
        conn.commit()
        conn.close()
        return False
    conn.close()
    return True


def get_user_settings(user_id: int) -> dict:
    """
    Retrieve user settings based on numeric user_id.
    Returns empty dict if user hasn't activated a key yet.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT * FROM user_settings WHERE user_id=?", (user_id,))
    row = c.fetchone()
    if row is None:
        # Return empty dict if user hasn't activated a key
        conn.close()
        return {}
    columns = [desc[0] for desc in c.description]
    conn.close()
    return dict(zip(columns, row))


def update_user_setting(user_id: int, field: str, value):
    """
    Update a specific user setting based on numeric user_id.
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        f"UPDATE user_settings SET {field}=? WHERE user_id=?", (value, user_id))
    conn.commit()
    conn.close()
