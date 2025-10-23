# Overview

This project is a Telegram cryptocurrency pump/dump monitoring bot developed in Python using aiogram 3.x. Its primary purpose is to track significant price movements (pumps or dumps) of cryptocurrencies across Binance and Bybit futures markets. Users receive real-time alerts based on configurable thresholds, including trading metrics like RSI, funding rates, and long/short ratios. The bot aims to provide timely insights for cryptocurrency traders, operating via a license key system and user-specific preferences stored in an SQLite database.

**Status**: ✅ Fully functional and production-ready (October 23, 2025)

**Recent Fix**: Database schema migration to support user_id columns for reliable user authentication. All activation flows tested and working correctly.

# User Preferences

Preferred communication style: Simple, everyday language.

# System Architecture

## Application Framework
- **Bot Framework**: aiogram 3.x
- **Async Runtime**: asyncio for concurrent operations
- **Programming Language**: Python 3.x

## Data Storage
- **Database**: SQLite (`keys.db`) for user settings and license keys.
  - `access_keys` table: Stores license keys, activation status, expiration, and **user_id** (numeric Telegram ID).
  - `user_settings` table: Stores user preferences including `user_id` (critical for Telegram API messaging), username, exchange selections, signal types, timeframes, thresholds, daily limits, and admin status.
- **Rationale**: Chosen for simplicity and low overhead for moderate user bases.
- **Migration**: `migrate_database.py` script available to update old databases without user_id column.

## Exchange Integration
- **Exchanges**: Binance (USDT-margined futures API: `/fapi/v1/klines`) and Bybit (Linear perpetual futures API: `/v5/market/kline?category=linear`).
- **Market Type**: Focuses on **futures markets** for alignment with funding rates and long/short ratios.
- **Concurrency Control**: Semaphore-based rate limiting (5 concurrent requests per exchange).
- **Proxy Support**: Configurable HTTP proxy for regional restrictions.
- **Design Pattern**: Separate API modules with unified response formats for metrics.

## Signal Detection Logic
- **Monitoring**: Background task `check_signals()` processes active users periodically.
- **Calculations**: Price change (open vs close) and volume analysis between candles.
- **Filtering**: User-configurable percentage thresholds trigger signals.
- **Rate Limiting**: Per-user daily signal caps with midnight resets.

## User Interface
- **Keyboard Menus**: ReplyKeyboardMarkup for main navigation and interaction.
- **Command Handlers**: `/start` for activation and message handlers for menu interactions.
- **Settings**: In-chat configuration of user preferences.

## Authentication & Authorization
- **License Key System**: Pre-generated keys with expiration; `ADMIN-ROOT-ACCESS` for administrators.
- **Activation Flow**: Users enter a key, which is validated against `access_keys` to create a `user_settings` record and grant access.
- **Session Management**: `user_states` dictionary tracks activation state using `user_id`.
- **Critical**: Uses immutable `user_id` (numeric Telegram ID) for authentication and messaging to prevent issues with username changes.

## Monitoring & Logging
- **Logging**: File-based `pumpscreener.log` for INFO-level events.
- **Deployment**: Designed for VPS deployment with systemd service (`pumpscreener.service`).

# External Dependencies

## Third-Party APIs
- **Binance REST API**: Public futures klines endpoint.
- **Bybit REST API**: Public linear perpetual futures kline endpoint.
- **CoinGlass API**: Optional advanced trading metrics (RSI, long/short ratios, funding rates). Requires `CG-API-KEY` header. The bot implements free alternatives if CoinGlass data is unavailable or requires a paid subscription.
- **Free Metrics**: Custom implementations for RSI, Funding Rate (from Binance/Bybit public APIs), and Long/Short Ratio (from Binance public API).

## Python Packages
- `aiogram` (>=3.0, <4.0): Telegram Bot API framework.
- `aiohttp`: Asynchronous HTTP client.
- `python-dateutil`: Date manipulation.

## Infrastructure Services
- **HTTP Proxy**: Configurable for API request routing.
- **Telegram Bot API**: Core communication platform.
- **SQLite**: Local file-based database.

## Configuration Dependencies
- Telegram bot token.
- CoinGlass API key (optional).
- Admin chat ID.
