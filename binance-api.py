# utils/binance_api.py
import aiohttp
import asyncio

from config import PROXY_URL

SEMAPHORE = asyncio.Semaphore(5)

# USDT-margined futures endpoint
BASE_URL = "https://fapi.binance.com/fapi/v1"

# --- Кеш для сохранения последних результатов price_change ---
import time
PRICE_CACHE: dict[tuple[str, str], dict] = {}
CACHE_TTL = 300  # время жизни кеша в секундах (5 минут)

async def get_klines(symbol: str, interval: str, limit: int = 2):
    url = f"{BASE_URL}/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    # ждём свободное "окно" семафора, чтобы не превысить 5 параллельных запросов
    async with SEMAPHORE:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, proxy=PROXY_URL) as resp:
                return await resp.json()

async def get_price_change(symbol: str, interval: str):
    """
    Вычисляет процент изменения цены и изменение объёма для symbol за 1 свечу.
    Теперь использует кеш: если с момента последнего запроса прошло меньше CACHE_TTL секунд,
    возвращает сохранённый результат, не обращаясь к Binance API.
    """
    key = (symbol, interval)
    now = time.time()
    # Если в кеше есть свежие данные — возвращаем их
    cached = PRICE_CACHE.get(key)
    if cached and now - cached["timestamp"] < CACHE_TTL:
        return cached["data"]

    # Иначе делаем реальный запрос
    klines = await get_klines(symbol, interval, limit=2)
    prev_kline, curr_kline = klines[0], klines[1]
    open_now = float(curr_kline[1])
    close_now = float(curr_kline[4])
    volume_prev = float(prev_kline[5])
    volume_now = float(curr_kline[5])

    price_change = ((close_now - open_now) / open_now) * 100
    volume_change = ((volume_now - volume_prev) / volume_prev) * 100 if volume_prev else 0.0

    result = {
        "price_change": price_change,
        "price_now": close_now,
        "volume_now": volume_now,
        "volume_prev": volume_prev,
        "volume_change": volume_change,
    }
    # Сохраняем результат в кеш с текущим временем
    PRICE_CACHE[key] = {"data": result, "timestamp": now}
    return result
