# utils/bybit_api.py
import aiohttp
import asyncio

SEMAPHORE = asyncio.Semaphore(5)

BASE_URL = "https://api.bybit.com/v5/market"

# Соответствие таймфреймов (минуты) для Bybit
INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
}

async def get_klines(symbol: str, interval: str, limit: int = 2):
    interval_val = INTERVAL_MAP[interval]
    url = f"{BASE_URL}/kline"
    params = {
        "category": "spot",
        "symbol": symbol,
        "interval": interval_val,
        "limit": limit,
    }
    async with SEMAPHORE:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
                return data["result"]["list"]

async def get_price_change(symbol: str, interval: str):
    """
    Аналогично Binance: берём две последние свечи и считаем % изменения.
    Формула такая же.
    """
    klines = await get_klines(symbol, interval, limit=2)
    prev_kline, curr_kline = klines[0], klines[1]
    open_now = float(curr_kline[1])  # openPrice
    close_now = float(curr_kline[4])  # closePrice
    volume_prev = float(prev_kline[5])  # volume
    volume_now = float(curr_kline[5])

    price_change = ((close_now - open_now) / open_now) * 100
    volume_change = ((volume_now - volume_prev) / volume_prev) * 100 if volume_prev else 0.0
    return {
        "price_change": price_change,
        "price_now": close_now,
        "volume_now": volume_now,
        "volume_prev": volume_prev,
        "volume_change": volume_change,
    }
