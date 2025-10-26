import aiohttp
from config import PROXY_URL


async def get_open_interest_binance(symbol: str) -> float:
    url = "https://fapi.binance.com/fapi/v1/openInterest"
    params = {"symbol": symbol}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    return float(data.get("openInterest", 0))


async def get_open_interest_bybit(symbol: str) -> float:
    url = "https://api.bybit.com/v5/market/open-interest"
    params = {"category": "linear", "symbol": symbol}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    # В Bybit данные лежат глубже: result -> list -> [0] -> openInterest
    result_list = data.get("result", {}).get("list", [])
    if not result_list:
        return 0.0
    return float(result_list[0].get("openInterest", 0))


async def get_orderbook_ratio_binance(symbol: str, depth: int = 50) -> float:
    url = "https://fapi.binance.com/fapi/v1/depth"
    params = {"symbol": symbol, "limit": depth}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    bids = sum(float(bid[1]) for bid in data.get("bids", []))
    asks = sum(float(ask[1]) for ask in data.get("asks", []))
    return bids / asks if asks else 0.0


async def get_orderbook_ratio_bybit(symbol: str, depth: int = 50) -> float:
    url = "https://api.bybit.com/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": depth}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    b_list = data.get("result", {}).get("b", [])
    a_list = data.get("result", {}).get("a", [])
    bids = sum(float(entry[1]) for entry in b_list)
    asks = sum(float(entry[1]) for entry in a_list)
    return bids / asks if asks else 0.0
