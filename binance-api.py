# utils/binance_api.py
import aiohttp

BASE_URL = "https://api.binance.com/api/v3"

async def get_klines(symbol: str, interval: str, limit: int = 2):
    """
    Получает последние limit свечей (klines) для указанного symbol и interval.
    Возвращает список свечей, где каждая свеча — это список:
    [open_time, open, high, low, close, volume, ...].
    """
    url = f"{BASE_URL}/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as resp:
            return await resp.json()

async def get_price_change(symbol: str, interval: str):
    """
    Вычисляет процент изменения цены и изменение объёма для symbol за 1 свечу.
    Берёт последние 2 свечи: предыдущую и текущую, и считает:
      price_change = (close_now - open_now) / open_now * 100
      volume_change = (volume_now - volume_prev) / volume_prev * 100
    Возвращает словарь с полями:
      'price_change' (float), 'volume_now' (float), 'volume_prev' (float),
      'price_now' (float)
    """
    klines = await get_klines(symbol, interval, limit=2)
    # Две последние свечи: [0] – предыдущая, [1] – текущая
    prev_kline, curr_kline = klines[0], klines[1]
    open_now = float(curr_kline[1])
    close_now = float(curr_kline[4])
    volume_prev = float(prev_kline[5])
    volume_now = float(curr_kline[5])

    price_change = ((close_now - open_now) / open_now) * 100
    # избегаем деления на ноль
    volume_change = ((volume_now - volume_prev) / volume_prev) * 100 if volume_prev else 0.0
    return {
        "price_change": price_change,
        "price_now": close_now,
        "volume_now": volume_now,
        "volume_prev": volume_prev,
        "volume_change": volume_change,
    }
