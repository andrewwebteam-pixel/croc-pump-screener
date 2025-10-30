import aiohttp

from config import PROXY_URL

__all__ = [
    "get_open_interest_binance",
    "get_open_interest_bybit",
    "get_orderbook_ratio_binance",
    "get_orderbook_ratio_bybit",
]


async def get_open_interest_binance(symbol: str) -> float:
    """Fetch the open interest for a symbol from Binance Futures.

    Parameters
    ----------
    symbol : str
        Futures trading pair symbol (e.g., ``"BTCUSDT"``).

    Returns
    -------
    float
        The open interest value for the given symbol. Returns ``0.0`` if the
        value is missing from the response.
    """
    url = "https://fapi.binance.com/fapi/v1/openInterest"
    params = {"symbol": symbol}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    return float(data.get("openInterest", 0))


async def get_open_interest_bybit(symbol: str) -> float:
    """Fetch the open interest for a symbol from Bybit Futures.

    Parameters
    ----------
    symbol : str
        Futures trading pair symbol (e.g., ``"BTCUSDT"``).

    Returns
    -------
    float
        The open interest value from the first entry in the response list. If
        no data is returned, or the result is empty, returns ``0.0``.
    """
    # Convert timeframe for Bybit API compatibility (default 5min)
    interval_map = {
        "1m": "1min",
        "5m": "5min",
        "15m": "15min",
        "30m": "30min",
        "1h": "1h",
        "4h": "4h",
        "1d": "1d",
    }
    # Bybit API requires intervalTime — use default if missing
    interval = interval_map.get("5m")

    url = "https://api.bybit.com/v5/market/open-interest"
    params = {"category": "linear", "symbol": symbol, "intervalTime": interval}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    result_list = data.get("result", {}).get("list", [])
    if not result_list:
        import logging
        logging.warning(f"No open interest data for {symbol} on Bybit: {data}")
        return 0.0
    try:
        entry = result_list[0]
        value = entry.get("openInterest") or entry.get("openInterestUsd", 0)
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def get_orderbook_ratio_binance(symbol: str, depth: int = 50) -> float:
    """Calculate the bid/ask volume ratio from the Binance order book.

    Parameters
    ----------
    symbol : str
        Futures trading pair symbol (e.g., ``"BTCUSDT"``).
    depth : int, optional
        Number of price levels to include in the calculation (default ``50``).

    Returns
    -------
    float
        The ratio of total bid volume to total ask volume. If there are no
        asks, returns ``0.0``.
    """
    url = "https://fapi.binance.com/fapi/v1/depth"
    params = {"symbol": symbol, "limit": depth}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    bids = sum(float(bid[1]) for bid in data.get("bids", []))
    asks = sum(float(ask[1]) for ask in data.get("asks", []))
    return bids / asks if asks else 0.0


async def get_orderbook_ratio_bybit(symbol: str, depth: int = 50) -> float:
    """Calculate the bid/ask volume ratio from the Bybit order book.

    Parameters
    ----------
    symbol : str
        Futures trading pair symbol (e.g., ``"BTCUSDT"``).
    depth : int, optional
        Number of price levels to include in the calculation (default ``50``).

    Returns
    -------
    float
        The ratio of total bid volume to total ask volume. If there are no
        asks, returns ``0.0``.
    """
    url = "https://api.bybit.com/v5/market/orderbook"
    params = {"category": "linear", "symbol": symbol, "limit": depth}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params, proxy=PROXY_URL) as resp:
            data = await resp.json()
    bids = data.get("result", {}).get("b", [])
    asks = data.get("result", {}).get("a", [])
    total_bids = sum(float(entry[1]) for entry in bids)
    total_asks = sum(float(entry[1]) for entry in asks)
    return total_bids / total_asks if total_asks else 0.0
