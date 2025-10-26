# utils/free_metrics.py
"""
Free alternative metrics using Binance and Bybit Futures APIs.
These APIs don't require authentication for public data.
"""

import aiohttp
import asyncio
from config import PROXY_URL

# Rate limiting
SEMAPHORE = asyncio.Semaphore(5)


async def get_funding_rate_free(exchange: str, symbol: str) -> float | None:
    """
    Get current funding rate from exchange futures API (FREE).

    Args:
        exchange: "Binance" or "Bybit"
        symbol: e.g., "BTCUSDT"

    Returns:
        Funding rate as percentage (e.g., 0.01 for 0.01%)
    """
    async with SEMAPHORE:
        try:
            if exchange.lower() == "binance":
                url = "https://fapi.binance.com/fapi/v1/fundingRate"
                params = {"symbol": symbol, "limit": 1}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data and len(data) > 0:
                                # Binance returns funding rate as decimal (e.g., 0.0001)
                                # Convert to percentage (e.g., 0.01%)
                                return float(data[0]["fundingRate"]) * 100

            elif exchange.lower() == "bybit":
                url = "https://api.bybit.com/v5/market/funding/history"
                params = {"category": "linear", "symbol": symbol, "limit": 1}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("retCode") == 0:
                                result = data.get("result", {}).get("list", [])
                                if result and len(result) > 0:
                                    # Bybit returns funding rate as decimal
                                    return float(result[0]["fundingRate"]) * 100

            return None
        except Exception:
            return None


async def get_long_short_ratio_free(symbol: str, period: str = "5m") -> tuple | None:
    """
    Get long/short ratio from Binance Futures API (FREE).

    Args:
        symbol: e.g., "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"

    Returns:
        Tuple of (long_percentage, short_percentage) or None
    """
    async with SEMAPHORE:
        try:
            url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            params = {"symbol": symbol, "period": period, "limit": 1}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and len(data) > 0:
                            ratio = float(data[0]["longShortRatio"])
                            # Convert ratio to percentages
                            # If ratio is 1.5, it means 1.5 longs for every 1 short
                            # Long% = 1.5 / (1.5 + 1) = 60%
                            # Short% = 1 / (1.5 + 1) = 40%
                            long_pct = (ratio / (ratio + 1)) * 100
                            short_pct = 100 - long_pct
                            return (long_pct, short_pct)

            return None
        except Exception:
            return None


async def calculate_rsi_simple(candles: list, period: int = 14) -> float | None:
    """
    Calculate RSI from a list of candles.

    Args:
        candles: List of price data (each with 'close' key)
        period: RSI period (default 14)

    Returns:
        RSI value (0-100) or None
    """
    try:
        if len(candles) < period + 1:
            return None

        # Extract close prices
        # Index 4 is close price in kline data
        closes = [float(c[4]) for c in candles]

        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]

        # Separate gains and losses
        gains = [max(0, change) for change in changes]
        losses = [abs(min(0, change)) for change in changes]

        # Calculate average gain and loss over period
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        # Avoid division by zero
        if avg_loss == 0:
            return 100.0

        # Calculate RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi, 2)
    except Exception:
        return None


async def get_rsi_from_exchange(exchange: str, symbol: str, interval: str = "15m") -> float | None:
    """
    Calculate RSI by fetching recent candles from exchange.

    Args:
        exchange: "Binance" or "Bybit"
        symbol: e.g., "BTCUSDT"
        interval: e.g., "15m", "1h"

    Returns:
        RSI value or None
    """
    async with SEMAPHORE:
        try:
            if exchange.lower() == "binance":
                # Use Binance USDT-margined futures for RSI calculation
                url = "https://fapi.binance.com/fapi/v1/klines"
                params = {"symbol": symbol, "interval": interval, "limit": 20}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            candles = await resp.json()
                            return await calculate_rsi_simple(candles)

            elif exchange.lower() == "bybit":
                # Bybit interval mapping
                interval_map = {"1m": "1", "5m": "5",
                                "15m": "15", "30m": "30", "1h": "60"}
                bybit_interval = interval_map.get(interval, "15")

                url = "https://api.bybit.com/v5/market/kline"
                # Use linear perpetual futures for RSI calculation
                params = {"category": "linear", "symbol": symbol,
                          "interval": bybit_interval, "limit": 20}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("retCode") == 0:
                                candles = data.get(
                                    "result", {}).get("list", [])
                                # Bybit returns in reverse order, so reverse it
                                candles = list(reversed(candles))
                                return await calculate_rsi_simple(candles)

            return None
        except Exception:
            return None

    # utils/free_metrics.py
"""
Free alternative metrics using Binance and Bybit Futures APIs.
These APIs don't require authentication for public data.
"""


# Rate limiting
SEMAPHORE = asyncio.Semaphore(5)


async def get_funding_rate_free(exchange: str, symbol: str) -> float | None:
    """
    Get current funding rate from exchange futures API (FREE).

    Args:
        exchange: "Binance" or "Bybit"
        symbol: e.g., "BTCUSDT"

    Returns:
        Funding rate as percentage (e.g., 0.01 for 0.01%)
    """
    async with SEMAPHORE:
        try:
            if exchange.lower() == "binance":
                url = "https://fapi.binance.com/fapi/v1/fundingRate"
                params = {"symbol": symbol, "limit": 1}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data and len(data) > 0:
                                # Binance returns funding rate as decimal (e.g., 0.0001)
                                # Convert to percentage (e.g., 0.01%)
                                return float(data[0]["fundingRate"]) * 100

            elif exchange.lower() == "bybit":
                url = "https://api.bybit.com/v5/market/funding/history"
                params = {"category": "linear", "symbol": symbol, "limit": 1}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("retCode") == 0:
                                result = data.get("result", {}).get("list", [])
                                if result and len(result) > 0:
                                    # Bybit returns funding rate as decimal
                                    return float(result[0]["fundingRate"]) * 100

            return None
        except Exception:
            return None


async def get_long_short_ratio_free(symbol: str, period: str = "5m") -> tuple | None:
    """
    Get long/short ratio from Binance Futures API (FREE).

    Args:
        symbol: e.g., "BTCUSDT"
        period: "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d"

    Returns:
        Tuple of (long_percentage, short_percentage) or None
    """
    async with SEMAPHORE:
        try:
            url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
            params = {"symbol": symbol, "period": period, "limit": 1}

            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data and len(data) > 0:
                            ratio = float(data[0]["longShortRatio"])
                            # Convert ratio to percentages
                            # If ratio is 1.5, it means 1.5 longs for every 1 short
                            # Long% = 1.5 / (1.5 + 1) = 60%
                            # Short% = 1 / (1.5 + 1) = 40%
                            long_pct = (ratio / (ratio + 1)) * 100
                            short_pct = 100 - long_pct
                            return (long_pct, short_pct)

            return None
        except Exception:
            return None


async def calculate_rsi_simple(candles: list, period: int = 14) -> float | None:
    """
    Calculate RSI from a list of candles.

    Args:
        candles: List of price data (each with 'close' key)
        period: RSI period (default 14)

    Returns:
        RSI value (0-100) or None
    """
    try:
        if len(candles) < period + 1:
            return None

        # Extract close prices
        # Index 4 is close price in kline data
        closes = [float(c[4]) for c in candles]

        # Calculate price changes
        changes = [closes[i] - closes[i-1] for i in range(1, len(closes))]

        # Separate gains and losses
        gains = [max(0, change) for change in changes]
        losses = [abs(min(0, change)) for change in changes]

        # Calculate average gain and loss over period
        avg_gain = sum(gains[-period:]) / period
        avg_loss = sum(losses[-period:]) / period

        # Avoid division by zero
        if avg_loss == 0:
            return 100.0

        # Calculate RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return round(rsi, 2)
    except Exception:
        return None


async def get_rsi_from_exchange(exchange: str, symbol: str, interval: str = "15m") -> float | None:
    """
    Calculate RSI by fetching recent candles from exchange.

    Args:
        exchange: "Binance" or "Bybit"
        symbol: e.g., "BTCUSDT"
        interval: e.g., "15m", "1h"

    Returns:
        RSI value or None
    """
    async with SEMAPHORE:
        try:
            if exchange.lower() == "binance":
                # Use Binance USDT-margined futures for RSI calculation
                url = "https://fapi.binance.com/fapi/v1/klines"
                params = {"symbol": symbol, "interval": interval, "limit": 20}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            candles = await resp.json()
                            return await calculate_rsi_simple(candles)

            elif exchange.lower() == "bybit":
                # Bybit interval mapping
                interval_map = {"1m": "1", "5m": "5",
                                "15m": "15", "30m": "30", "1h": "60"}
                bybit_interval = interval_map.get(interval, "15")

                url = "https://api.bybit.com/v5/market/kline"
                # Use linear perpetual futures for RSI calculation
                params = {"category": "linear", "symbol": symbol,
                          "interval": bybit_interval, "limit": 20}

                async with aiohttp.ClientSession() as session:
                    async with session.get(url, params=params, proxy=PROXY_URL, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("retCode") == 0:
                                candles = data.get(
                                    "result", {}).get("list", [])
                                # Bybit returns in reverse order, so reverse it
                                candles = list(reversed(candles))
                                return await calculate_rsi_simple(candles)

            return None
        except Exception:
            return None

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
        # ориентируемся на поле openInterest в первой записи списка
        return float(data["result"]["list"][0]["openInterest"])

    async def get_orderbook_ratio_binance(symbol: str, depth: int = 50) -> float:
        url = "https://fapi.binance.com/fapi/v1/depth"
        params = {"symbol": symbol, "limit": depth}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, proxy=PROXY_URL) as resp:
                data = await resp.json()
        bids = sum(float(bid[1]) for bid in data["bids"])
        asks = sum(float(ask[1]) for ask in data["asks"])
        return bids / asks if asks else 0.0

    async def get_orderbook_ratio_bybit(symbol: str, depth: int = 50) -> float:
        url = "https://api.bybit.com/v5/market/orderbook"
        params = {"category": "linear", "symbol": symbol, "limit": depth}
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, proxy=PROXY_URL) as resp:
                data = await resp.json()
        bids = sum(float(entry[1]) for entry in data["result"]["b"])
        asks = sum(float(entry[1]) for entry in data["result"]["a"])
        return bids / asks if asks else 0.0
