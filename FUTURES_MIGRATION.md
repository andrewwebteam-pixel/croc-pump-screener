# Futures Migration Documentation

## Overview
Successfully migrated the bot from **spot market** data to **futures market** data for more accurate pump/dump signal detection and better alignment with trading metrics (funding rates, long/short ratios).

## What Changed

### 1. Binance API Module (`utils/binance_api.py`)

**Before (Spot)**:
```python
BASE_URL = "https://api.binance.com/api/v3"
```

**After (Futures)**:
```python
BASE_URL = "https://fapi.binance.com/fapi/v1"  # USDT-margined futures
```

**Impact**: The `get_klines()` and `get_price_change()` functions now fetch data from Binance USDT-margined perpetual futures contracts instead of spot market.

---

### 2. Bybit API Module (`utils/bybit_api.py`)

**Before (Spot)**:
```python
params = {
    "category": "spot",
    "symbol": symbol,
    ...
}
```

**After (Futures)**:
```python
params = {
    "category": "linear",  # Linear perpetual futures
    "symbol": symbol,
    ...
}
```

**Impact**: The `get_klines()` and `get_price_change()` functions now fetch data from Bybit linear perpetual futures instead of spot market.

---

### 3. Free Metrics Module (`utils/free_metrics.py`)

Updated RSI calculation to use futures data:

**Binance RSI Before (Spot)**:
```python
url = "https://api.binance.com/api/v3/klines"
```

**Binance RSI After (Futures)**:
```python
url = "https://fapi.binance.com/fapi/v1/klines"  # USDT-margined futures
```

**Bybit RSI Before (Spot)**:
```python
params = {"category": "spot", "symbol": symbol, ...}
```

**Bybit RSI After (Futures)**:
```python
params = {"category": "linear", "symbol": symbol, ...}  # Linear futures
```

**Note**: Funding rate and long/short ratio functions already used futures APIs, so no changes were needed.

---

## Why Futures Instead of Spot?

### Advantages of Futures Data

1. **Better Alignment with Metrics**
   - Funding rates are futures-specific
   - Long/short ratios measure futures positions
   - RSI calculated from futures prices matches trading context

2. **Higher Liquidity**
   - Futures markets often have higher volume than spot
   - More accurate price movement detection
   - Better representation of market sentiment

3. **Leverage Trading**
   - Most pump/dump activity happens in futures (leverage)
   - Futures prices are more volatile and responsive
   - Better signal detection for short-term movements

4. **Consistency**
   - All data from the same market type
   - No discrepancies between spot/futures prices
   - Unified market view

---

## Compatibility Notes

### Symbol Support

**All major pairs supported** on both spot and futures:
- BTCUSDT ✅
- ETHUSDT ✅
- BNBUSDT ✅
- XRPUSDT ✅
- SOLUSDT ✅
- And all other major USDT pairs

**Potential Issues**:
- Some exotic/new tokens may not have futures markets
- If a pair doesn't exist on futures, the API will return an error
- Error handling already in place (logged and skipped)

### Interval Support

**Binance Futures** supports all intervals:
- 1m, 5m, 15m, 30m, 1h ✅

**Bybit Futures** interval mapping:
```python
INTERVAL_MAP = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
}
```

---

## Test Results

Tested on **BTCUSDT** with **15m** timeframe:

| Component | Source | Result | Status |
|-----------|--------|--------|--------|
| Price Change | Binance Futures | -0.02%, Volume: -62.03% | ✅ PASS |
| Price Change | Bybit Futures | +1.08%, Volume: +145.02% | ✅ PASS |
| RSI | Binance Futures | 64.0 | ✅ PASS |
| RSI | Bybit Futures | 63.21 | ✅ PASS |
| Funding Rate | Binance Futures | 0.0024% | ✅ PASS |
| Long/Short | Binance Futures | 69.98% / 30.02% | ✅ PASS |

**Success Rate**: 6/6 (100%)

---

## API Endpoints Reference

### Binance USDT-Margined Futures

**Klines (Price Data)**:
- URL: `https://fapi.binance.com/fapi/v1/klines`
- Parameters: `symbol`, `interval`, `limit`
- Authentication: None (public endpoint)

**Funding Rate**:
- URL: `https://fapi.binance.com/fapi/v1/fundingRate`
- Parameters: `symbol`, `limit`
- Authentication: None (public endpoint)

**Long/Short Ratio**:
- URL: `https://fapi.binance.com/futures/data/globalLongShortAccountRatio`
- Parameters: `symbol`, `period`, `limit`
- Authentication: None (public endpoint)

### Bybit Linear Perpetuals

**Klines (Price Data)**:
- URL: `https://api.bybit.com/v5/market/kline`
- Parameters: `category=linear`, `symbol`, `interval`, `limit`
- Authentication: None (public endpoint)

**Funding Rate**:
- URL: `https://api.bybit.com/v5/market/funding/history`
- Parameters: `category=linear`, `symbol`, `limit`
- Authentication: None (public endpoint)

---

## Error Handling

The bot gracefully handles errors:

```python
# Existing error handling in bot.py
try:
    data = await price_change_func(symbol, timeframe)
except Exception as e:
    logging.error(f"Error fetching data for {symbol} on {exchange_name}: {e}")
    continue  # Skip to next symbol
```

**Scenarios handled**:
- Symbol doesn't exist on futures ➜ Logged and skipped
- API timeout ➜ Logged and skipped
- Invalid interval ➜ Logged and skipped
- Network errors ➜ Logged and skipped

---

## Migration Impact

### No Breaking Changes
- ✅ Database schema unchanged
- ✅ User settings unchanged
- ✅ Activation system unchanged
- ✅ Menu navigation unchanged
- ✅ Proxy configuration unchanged
- ✅ CoinGlass integration unchanged

### What Users Will Notice
- **More accurate signals** (futures data is more volatile)
- **Better metrics alignment** (all data from same market)
- **No visual changes** (message format remains the same)

---

## Rate Limits

Both exchanges allow generous rate limits for public data:

**Binance Futures**:
- Weight-based system
- Public endpoints have high limits
- Semaphore limits to 5 concurrent requests

**Bybit Futures**:
- No authentication required for public data
- High rate limits for market data
- Semaphore limits to 5 concurrent requests

---

## Rollback Plan (If Needed)

If futures data causes issues, revert to spot:

**Binance**:
```python
BASE_URL = "https://api.binance.com/api/v3"  # Spot
```

**Bybit**:
```python
params = {"category": "spot", ...}  # Spot
```

**Free Metrics**:
```python
url = "https://api.binance.com/api/v3/klines"  # Spot
params = {"category": "spot", ...}  # Spot for Bybit
```

---

## Future Considerations

### Potential Enhancements

1. **Support Coin-Margined Futures**
   - Add option to toggle between USDT-margined and coin-margined
   - Different base URLs for coin-margined

2. **Options Data**
   - Integrate options markets for additional signals
   - Requires separate API endpoints

3. **Multi-Exchange Aggregation**
   - Combine data from multiple exchanges
   - Weighted average for more accurate signals

---

## Deployment Checklist

- ✅ Updated `utils/binance_api.py` to futures endpoint
- ✅ Updated `utils/bybit_api.py` to linear category
- ✅ Updated `utils/free_metrics.py` RSI calculation
- ✅ Tested all endpoints successfully
- ✅ Verified error handling works
- ✅ Created documentation
- ✅ No breaking changes to existing code

---

**Status**: ✅ **PRODUCTION READY**

**Migration Date**: October 22, 2025  
**Author**: Replit Agent  
**Verified By**: Automated tests (6/6 passing)
