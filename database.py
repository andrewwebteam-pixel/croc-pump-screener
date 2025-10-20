import sqlite3
from datetime import datetime
from dateutil.relativedelta import relativedelta  # понадобится пакет python-dateutil

DB_PATH = "keys.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS access_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            access_key TEXT UNIQUE NOT NULL,
            username TEXT,
            duration_months INTEGER NOT NULL,
            activated_at DATETIME,
            expires_at DATETIME,
            is_active INTEGER DEFAULT 0
        )
    """)
    # user_settings таблица остаётся прежней (если вы её уже добавили)
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
    """Активировать ключ и привязать его к пользователю, если он ещё не использован."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT duration_months, is_active, username FROM access_keys WHERE access_key = ?", (access_key,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    duration_months, is_active, existing_user = row
    if is_active == 1:
        # ключ уже активирован; разрешить только тому же пользователю
        conn.close()
        return existing_user == username
    # активируем ключ
    now = datetime.utcnow()
    expires_at = now + relativedelta(months=duration_months)
    c.execute(
        "UPDATE access_keys SET username = ?, activated_at = ?, expires_at = ?, is_active = 1 WHERE access_key = ?",
        (username, now, expires_at, access_key),
    )
    conn.commit()
    conn.close()
    return True

def check_subscription(username: str) -> bool:
    """Проверить, активен ли ключ пользователя и не истёк ли его срок."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT expires_at FROM access_keys WHERE username = ? AND is_active = 1", (username,))
    row = c.fetchone()
    if row is None:
        conn.close()
        return False
    expires_at_str = row[0]
    expires_at = datetime.fromisoformat(expires_at_str)
    if datetime.utcnow() >= expires_at:
        # истёк срок действия, деактивируем
        c.execute("UPDATE access_keys SET is_active = 0 WHERE username = ?", (username,))
        conn.commit()
        conn.close()
        return False
    conn.close()
    return True
