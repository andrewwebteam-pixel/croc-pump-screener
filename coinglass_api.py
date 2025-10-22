# utils/coinglass_api.py
import aiohttp
import asyncio
from config import COINGLASS_API_KEY

# Ограничиваем число одновременных запросов к CoinGlass
SEMAPHORE = asyncio.Semaphore(5)

# Базовые адреса API CoinGlass
BASE_URL_V4 = "https://open-api-v4.coinglass.com/api"
BASE_URL_V2 = "https://open-api.coinglass.com/public/v2"

async def _fetch_json(url: str, params: dict | None = None) -> dict:
    """Вспомогательная функция для GET‑запросов."""
    async with SEMAPHORE:
        headers = {
            "accept": "application/json",
            "coinglassSecret": COINGLASS_API_KEY,
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers) as resp:
                return await resp.json()

async def get_rsi(symbol: str, interval: str) -> float | None:
    """
    Получает значение RSI для указанной пары и таймфрейма.
    По открытой документации v4 endpoint 'futures/rsi/list' возвращает RSI по нескольким таймфреймам.
    """
    # Отправляем запрос на список RSI для фьючерсов.
    url = f"{BASE_URL_V4}/futures/rsi/list"
    try:
        data = await _fetch_json(url, params={"symbol": symbol})
        # Ожидаемый формат: {"data": {"symbol": {"rsi_15m": value, "rsi_1h": value, ...}}}
        symbol_data = data.get("data", {}).get(symbol)
        if not symbol_data:
            return None
        # Соответствие таймфреймов ключам ответа
        tf_map = {
            "1m": "rsi_1m", "5m": "rsi_5m",
            "15m": "rsi_15m", "30m": "rsi_30m",
            "1h": "rsi_1h"
        }
        key = tf_map.get(interval)
        return float(symbol_data.get(key)) if key and symbol_data.get(key) else None
    except Exception:
        return None

async def get_long_short_ratio(symbol: str, time_type: str = "h1") -> tuple | None:
    """
    Получает соотношение Long/Short для указанной пары.
    В API v2 endpoint 'long_short' возвращает данные по биржам.
    time_type: h1, h4, h12, h24 и т.п.
    Возвращает кортеж (доля лонгов, доля шортов) в процентах.
    """
    url = f"{BASE_URL_V2}/long_short"
    try:
        data = await _fetch_json(url, params={"symbol": symbol, "time_type": time_type})
        # 'data' содержит список бирж с данными о long/short ratio
        entries = data.get("data")
        if not entries:
            return None
        # Берём агрегированное значение по всем биржам (первая запись)
        first_entry = entries[0]
        long_ratio = float(first_entry.get("longVolPct", 0))
        short_ratio = float(first_entry.get("shortVolPct", 0))
        return long_ratio, short_ratio
    except Exception:
        return None

async def get_funding_rate(exchange: str, pair: str, interval: str = "h1") -> float | None:
    """
    Получает текущий funding rate для пары на заданной бирже.
    В API v2 endpoint 'indicator/funding' требует параметры:
      ex — название биржи (Binance, Bybit и др.);
      pair — пара (например, BTCUSDT);
      interval — интервал (m1, m5, h1 и т.п.).
    """
    url = f"{BASE_URL_V2}/indicator/funding"
    try:
        data = await _fetch_json(url, params={"ex": exchange, "pair": pair, "interval": interval, "limit": 1})
        # Ответ содержит список словарей; берём первое значение
        rates = data.get("data")
        if not rates:
            return None
        rate = float(rates[0].get("fundingRate", 0))
        return rate
    except Exception:
        return None
