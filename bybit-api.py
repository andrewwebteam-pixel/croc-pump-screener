# utils/bybit_api.py
import time
import aiohttp
import asyncio

from config import PROXY_URL

SEMAPHORE = asyncio.Semaphore(5)

BASE_URL = "https://api.bybit.com/v5/market"

# --- Кеш для сохранения последних результатов price_change ---
PRICE_CACHE: dict[tuple[str, str], dict] = {}
CACHE_TTL = 300  # время жизни кеша (5 минут)

# Соответствие таймфреймов (минуты) для Bybit
INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "4h": "240",
    "1d": "D",
    "1w": "W",
    "1M": "M",
}


async def get_klines(symbol: str, interval: str, limit: int = 2):
    interval_val = INTERVAL_MAP[interval]
    url = f"{BASE_URL}/kline"
    params = {
        "category": "linear",  # Linear perpetual futures
        "symbol": symbol,
        "interval": interval_val,
        "limit": limit,
    }
    async with SEMAPHORE:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, proxy=PROXY_URL) as resp:
                data = await resp.json()
                return data["result"]["list"]


async def get_price_change(symbol: str, interval: str):
    """
    Аналогично Binance: берём две последние свечи и считаем % изменения.
    Использует кеш, чтобы не запрашивать одинаковые данные несколько раз в течение CACHE_TTL секунд.
    """
    key = (symbol, interval)
    now = time.time()
    cached = PRICE_CACHE.get(key)
    if cached and now - cached["timestamp"] < CACHE_TTL:
        return cached["data"]

    klines = await get_klines(symbol, interval, limit=2)
    prev_kline, curr_kline = klines[0], klines[1]
    open_now = float(curr_kline[1])
    close_now = float(curr_kline[4])
    volume_prev = float(prev_kline[5])
    volume_now = float(curr_kline[5])

    price_change = ((close_now - open_now) / open_now) * 100
    volume_change = ((volume_now - volume_prev) /
                     volume_prev) * 100 if volume_prev else 0.0

    result = {
        "price_change": price_change,
        "price_now": close_now,
        "volume_now": volume_now,
        "volume_prev": volume_prev,
        "volume_change": volume_change,
    }
    PRICE_CACHE[key] = {"data": result, "timestamp": now}
    return result
