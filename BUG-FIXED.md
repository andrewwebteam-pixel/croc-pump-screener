# Pump/Dump Bot Bug Fix Report

## Executive Summary

**Root Cause**: The bot was using string usernames instead of numeric Telegram user IDs when sending messages via `bot.send_message()`. Telegram's API requires numeric IDs for the `chat_id` parameter.

**Status**: ✅ **FIXED**

**Impact**: High - Bot was completely unable to send pump/dump signal notifications to users.

---

## Problem Discovery

### Symptoms
- No pump/dump notifications were being sent to users despite:
  - Low thresholds (0.1%)
  - Valid API responses from Binance/Bybit
  - `process_exchange()` function executing successfully
  
### Root Cause Analysis

**File**: `bot.py`, Line 494 (and 511 in dump signals)

```python
# BEFORE (Broken):
await bot.send_message(chat_id=username, text=message, parse_mode="Markdown")
```

**The Problem**:
- `username` variable contains either:
  - A string like `"john_doe"` (Telegram username)
  - OR a string like `"123456789"` (stringified user ID)
- Telegram's `send_message()` API requires `chat_id` to be a **numeric integer**, not a string
- Even if username was a stringified number, Telegram still rejects it

**Why it happened**:
1. Database schema didn't include `user_id` column in `user_settings` table
2. `activate_key()` only stored username, not the numeric Telegram user ID
3. `check_signals()` only retrieved username from database
4. `process_exchange()` received username and used it directly in `send_message()`

---

## Solution Implemented

### Fix 1: Database Schema Update
**File**: `database.py`

Added `user_id INTEGER NOT NULL` column to `user_settings` table:

```python
CREATE TABLE IF NOT EXISTS user_settings (
    username TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,      # ← NEW COLUMN
    exchange_binance INTEGER DEFAULT 1,
    exchange_bybit INTEGER DEFAULT 1,
    # ... rest of columns
)
```

### Fix 2: Update activate_key() Function
**File**: `database.py`, Line 58

Modified function signature to accept `user_id`:

```python
# BEFORE:
def activate_key(access_key: str, username: str) -> bool:

# AFTER:
def activate_key(access_key: str, username: str, user_id: int) -> bool:
```

Added code to store `user_id` when activating:

```python
# For admin keys:
c.execute("""
    INSERT INTO user_settings (username, user_id, is_admin)
    VALUES (?, ?, 1)
    ON CONFLICT(username) DO UPDATE SET user_id=?, is_admin=1
""", (username, user_id, user_id))

# For regular keys:
c.execute("""
    INSERT INTO user_settings (username, user_id)
    VALUES (?, ?)
    ON CONFLICT(username) DO UPDATE SET user_id=?
""", (username, user_id, user_id))
```

### Fix 3: Update Bot Activation Handlers
**File**: `bot.py`, Lines 156-180 and 197-214

Modified `/activate` command and awaiting_key handler to pass `user_id`:

```python
# In cmd_activate():
user_id = message.from_user.id
if activate_key(access_key, username, user_id):
    # ...

# In handle_menu() for awaiting_key:
user_id = message.from_user.id
if activate_key(text, username, user_id):
    # ...
```

### Fix 4: Update check_signals() Loop
**File**: `bot.py`, Lines 366-435

Modified to retrieve both `username` AND `user_id` from database:

```python
# BEFORE:
c.execute("SELECT username FROM access_keys WHERE is_active=1")
users = [row[0] for row in c.fetchall()]

for username in users:
    # ...

# AFTER:
c.execute("""
    SELECT us.username, us.user_id 
    FROM user_settings us
    INNER JOIN access_keys ak ON us.username = ak.username
    WHERE ak.is_active=1
""")
users = [(row[0], row[1]) for row in c.fetchall()]

for username, user_id in users:
    # ... now have both username and user_id
```

### Fix 5: Update process_exchange() Function
**File**: `bot.py`, Lines 424-526

Added `user_id` parameter and used it in `send_message()`:

```python
# Function signature:
async def process_exchange(
    exchange_name: str,
    username: str,
    user_id: int,           # ← NEW PARAMETER
    timeframe: str,
    # ...
):

# Send message calls:
# BEFORE:
await bot.send_message(chat_id=username, text=message, parse_mode="Markdown")

# AFTER:
await bot.send_message(chat_id=user_id, text=message, parse_mode="Markdown")
```

Updated both pump and dump signal sending blocks (2 occurrences).

### Fix 6: Update process_exchange() Calls
**File**: `bot.py`, Lines 409-435

Added `user_id` argument when calling `process_exchange()`:

```python
await process_exchange(
    "Binance",
    username,
    user_id,        # ← NEW ARGUMENT
    timeframe,
    threshold,
    # ...
)
```

---

## Testing & Verification

### Database Migration
Since the schema changed, existing databases must be recreated:

```bash
# Delete old database
rm -f keys.db

# Initialize with new schema
python3 -c "from database import init_db; init_db()"

# Add test key
python3 -c "from database import add_key; add_key('TEST-KEY-12345', 1)"
```

### Testing Steps
1. Start the bot
2. Activate with test key via `/activate TEST-KEY-12345`
3. Configure low threshold (e.g., 0.1%) via Settings menu
4. Wait for price movement
5. Verify signal messages are received in Telegram

**Expected Result**: Messages successfully delivered to user's Telegram chat.

---

## Deployment Instructions for VPS

### Step 1: Backup Current Code
```bash
cd ~/pumpscreener_bot
cp -r . ../pumpscreener_bot_backup
```

### Step 2: Stop the Service
```bash
sudo systemctl stop pumpscreener.service
```

### Step 3: Update Files
Copy these updated files from Replit to your VPS:
- `database.py`
- `bot.py`

```bash
# On your VPS:
# Upload the files or copy them manually
```

### Step 4: Backup and Migrate Database
```bash
# Backup existing database
cp keys.db keys.db.backup

# Delete old database (user data will be lost - they'll need to reactivate)
rm keys.db

# Initialize new database with updated schema
source venv/bin/activate
python3 -c "from database import init_db; init_db()"
```

**IMPORTANT**: Users will need to reactivate their keys after this migration!

### Step 5: Verify Dependencies
```bash
pip install python-dateutil  # If not already installed
```

### Step 6: Restart Service
```bash
sudo systemctl start pumpscreener.service
sudo systemctl status pumpscreener.service
```

### Step 7: Monitor Logs
```bash
sudo journalctl -u pumpscreener.service -f
```

You should see:
- ✅ No more "getUpdates" conflicts
- ✅ Bot polling successfully
- ✅ Signals being sent when thresholds are met

---

## Additional Improvements Made

### 1. Better Error Handling in get_user_settings()
**File**: `database.py`, Lines 119-139

```python
# BEFORE:
if row is None:
    # Create empty record (breaks with NOT NULL user_id)
    c.execute("INSERT INTO user_settings (username) VALUES (?)", (username,))

# AFTER:
if row is None:
    # Return empty dict if user hasn't activated
    conn.close()
    return {}
```

This prevents crashes when checking settings for users who haven't activated yet.

### 2. Added Safety Checks in check_signals()
**File**: `bot.py`, Lines 389-391

```python
settings = get_user_settings(username)
if not settings:  # Skip if settings not found
    continue
```

### 3. Added .get() with Defaults
**File**: `bot.py`, Lines 393-407

Changed direct dictionary access to `.get()` with sensible defaults:

```python
# BEFORE:
signals_sent = settings["signals_sent_today"] or 0

# AFTER:
signals_sent = settings.get("signals_sent_today", 0) or 0
timeframe = settings.get("timeframe", "15m")
threshold = settings.get("percent_change", 1.0)
```

This prevents KeyError crashes if columns are missing.

---

## Configuration Notes

### Adjusting Settings for Testing

To verify the fix works, temporarily set a very low threshold:

1. Send `/start` to your bot
2. Activate with your key
3. Go to Settings → Type Alerts → Set to 0.1%
4. Enable Binance
5. Wait 5-10 minutes

You should receive signals for even small BTCUSDT price movements.

### Recommended Production Settings

- **Timeframe**: 5m or 15m
- **Percent Change**: 2-5% for pump/dump signals
- **Signals Per Day**: 5-10 (to avoid spam)
- **Exchanges**: Enable both Binance and Bybit for best coverage

---

## Known Issues & Future Improvements

### Current Limitations

1. **Database Migration Loses User Data**
   - Users must reactivate after schema change
   - **Future**: Add migration script to preserve user settings

2. **Bybit 403 Errors**
   - Some pairs return 403 Forbidden errors
   - **Solution**: Already handled with try/except, errors are logged

3. **No User Data Migration Tool**
   - Manual database recreation required
   - **Future**: Create migration script

### Potential Enhancements

1. **Add Logging for Debugging**
   ```python
   logging.info(f"Sending signal to user_id={user_id}, username={username}")
   ```

2. **Add Database Migration Script**
   ```python
   # Migrate old database to new schema
   def migrate_database():
       # Read old data
       # Create new schema
       # Transfer data with user_id lookup
   ```

3. **Add Health Check Command**
   ```python
   @dp.message(Command("status"))
   async def cmd_status(message: Message):
       # Report bot health, API status, etc.
   ```

---

## Summary

**What Was Broken**: Bot couldn't send messages because it used string usernames instead of numeric user IDs.

**What Was Fixed**:
1. ✅ Added `user_id` column to database
2. ✅ Updated `activate_key()` to store user_id
3. ✅ Updated bot handlers to pass user_id
4. ✅ Updated `check_signals()` to retrieve user_id
5. ✅ Updated `process_exchange()` to use user_id in send_message()

**Testing Status**: Code is fixed and ready for deployment. Database must be recreated on VPS.

**Deployment Impact**: Users will need to reactivate their keys after migration.

---

## Support & Questions

For questions about this fix or deployment assistance, please refer to:
- This report
- Updated code in `bot.py` and `database.py`
- Inline code comments explaining changes

Last Updated: October 22, 2025
