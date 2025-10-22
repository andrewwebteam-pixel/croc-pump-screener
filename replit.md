# Overview

This is a **Telegram cryptocurrency pump/dump monitoring bot** built with Python and aiogram 3.x. The bot tracks price movements across Binance and Bybit exchanges, alerting users when cryptocurrencies experience significant price changes (pumps or dumps) based on configurable thresholds. Users activate the bot via license keys stored in SQLite, configure their preferences (exchanges, timeframes, thresholds), and receive real-time alerts with trading metrics including RSI, funding rates, and long/short ratios from CoinGlass API.

**Deployment**: This bot runs on a VPS (not Replit) to avoid Telegram API polling conflicts. Replit is used for development and testing only.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Application Framework
- **Bot Framework**: aiogram 3.x for Telegram bot integration
- **Async Runtime**: asyncio-based architecture for concurrent API requests and background monitoring
- **Programming Language**: Python 3.x

## Data Storage
- **Database**: SQLite with two primary tables:
  - `access_keys`: Stores license keys with activation status, duration, and expiration tracking
  - `user_settings`: Stores per-user preferences including **username AND user_id** (both required), exchange selections, signal types, timeframes, thresholds, daily limits, and admin status
- **Rationale**: SQLite chosen for simplicity and low overhead in single-instance deployments; suitable for moderate user bases without requiring external database infrastructure
- **Critical**: `user_id` (numeric Telegram ID) is required for sending messages via Telegram API - using username strings causes message delivery failures

## Exchange Integration
- **Binance API**: REST endpoint `/api/v3/klines` for candlestick data
- **Bybit API**: REST endpoint `/v5/market/kline` for spot market data
- **Concurrency Control**: Semaphore-based rate limiting (5 concurrent requests per exchange) to avoid API throttling
- **Proxy Support**: HTTP proxy configuration for bypassing regional restrictions
- **Design Pattern**: Separate API modules (`binance_api.py`, `bybit_api.py`) with unified response format for price change and volume metrics

## Signal Detection Logic
- **Monitoring Loop**: Background task `check_signals()` periodically processes active users
- **Price Change Calculation**: Compares current candle (open vs close) to determine percentage movement
- **Volume Analysis**: Tracks volume changes between consecutive candles
- **Threshold Filtering**: User-configurable percentage thresholds determine signal triggers
- **Rate Limiting**: Per-user daily signal caps (`signals_per_day`) with automatic midnight resets

## User Interface
- **Keyboard Menus**: ReplyKeyboardMarkup for main navigation (Pump Alerts, Dump Alerts, Settings, My Tier, Logout)
- **Command Handlers**: `/start` for activation flow, message handlers for menu interactions
- **Settings Management**: In-chat configuration of exchanges, signal types, timeframes, and thresholds

## Authentication & Authorization
- **License Key System**: Pre-generated keys with configurable duration (months-based expiration)
- **Admin Key**: Special unlimited-access key (`ADMIN-ROOT-ACCESS`) for administrative users
- **Activation Flow**: Users enter license key → validates against `access_keys` table → creates `user_settings` record → grants access
- **Session Management**: `user_states` dictionary tracks activation state (awaiting key input)

## Monitoring & Logging
- **File-based Logging**: `pumpscreener.log` with timestamped entries for INFO-level events
- **Deployment**: systemd service (`pumpscreener.service`) for production runtime

# External Dependencies

## Third-Party APIs
- **Binance REST API**: Public klines endpoint for spot market data
  - Authentication: Not required for public endpoints
  - Rate Limiting: Handled via semaphore (5 concurrent requests)
  - Proxy: Configured via `PROXY_URL`

- **Bybit REST API**: Market data endpoints (`/v5/market/kline`)
  - Authentication: Not required for public spot data
  - Category: Spot market
  - Interval Mapping: Custom mapping for timeframe conversion (1m→1, 5m→5, etc.)
  - Known Issue: Some pairs return 403 errors

- **CoinGlass API**: Advanced trading metrics
  - Endpoints: RSI (`/futures/rsi/list`), long/short ratios, funding rates
  - Authentication: API key via `coinglassSecret` header
  - Optional: Bot functions without CoinGlass data if unavailable

## Python Packages
- `aiogram` (>=3.0, <4.0): Telegram Bot API framework
- `aiohttp`: Async HTTP client for exchange API requests
- `python-binance`: Binance SDK (imported but not actively used in current implementation)
- `pybit`: Bybit SDK (imported but not actively used in current implementation)
- `python-dateutil`: Date manipulation for key expiration calculations

## Infrastructure Services
- **HTTP Proxy**: `http://user191751:avldk7@93.127.153.92:9734` for API request routing
- **Telegram Bot API**: Message delivery and user interaction platform
- **SQLite**: Local file-based database (`keys.db`)

## Configuration Dependencies
- Telegram bot token stored in `config.py`
- Exchange API keys (Binance, Bybit) - currently unused but configured
- CoinGlass API key for enhanced metrics
- Admin chat ID for privileged access

# Recent Changes

## October 22, 2025 - Critical Bug Fix: Message Delivery Failure

**Problem**: Bot was unable to send pump/dump signal notifications to users.

**Root Cause**: `bot.send_message()` was using string username instead of numeric user_id for `chat_id` parameter. Telegram's API requires numeric integer IDs.

**Solution Applied**:
1. ✅ Added `user_id INTEGER NOT NULL` column to `user_settings` table
2. ✅ Updated `activate_key()` to accept and store user_id from `message.from_user.id`
3. ✅ Updated `/activate` command and awaiting_key handler to pass user_id
4. ✅ Updated `check_signals()` to JOIN user_settings and retrieve both username and user_id
5. ✅ Updated `process_exchange()` to accept user_id and use it in all `bot.send_message()` calls
6. ✅ Added safety checks in `get_user_settings()` to return empty dict for non-activated users
7. ✅ Added `.get()` methods with defaults to prevent KeyError crashes

**Deployment Impact**: 
- Database schema changed - existing databases must be recreated
- All users must reactivate their keys after migration
- See `BUGFIX_REPORT.md` for complete deployment instructions

**Files Changed**: `database.py`, `bot.py`
