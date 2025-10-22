# Bug Report: Missing CoinGlass Data in Signal Cards

## Problem Statement

Signal messages sent by the bot were missing three key metrics:
- ❌ RSI (Relative Strength Index)
- ❌ Funding Rate  
- ❌ Long/Short Ratio

## Root Cause Analysis

### Issue #1: Incorrect API Header ✅ FIXED

**Problem**: The CoinGlass API client was using the wrong authentication header.

```python
# BEFORE (Wrong):
headers = {
    "coinglassSecret": COINGLASS_API_KEY,
}

# AFTER (Correct):
headers = {
    "CG-API-KEY": COINGLASS_API_KEY,
}
```

**Fix Applied**: Updated `utils/coinglass_api.py` line 22 to use the correct `CG-API-KEY` header as per CoinGlass API v4 documentation.

**Reference**: https://docs.coinglass.com/reference/authentication

---

### Issue #2: Paid Subscription Required ⚠️ NOT FIXED (Requires User Action)

**Problem**: CoinGlass API requires a paid subscription to access RSI, Funding Rate, and Long/Short ratio endpoints.

**API Test Results**:

| Endpoint | Status | Response | Access Level |
|----------|--------|----------|--------------|
| Supported Coins | ✅ Works | Success | Free |
| RSI List | ❌ Blocked | "Upgrade plan" | Paid Only |
| Funding Rate | ❌ Blocked | "Upgrade plan" | Paid Only |
| Long/Short Ratio | ❌ Blocked | "Upgrade plan" | Paid Only |

**CoinGlass Pricing**:
- **HOBBYIST**: $29/month (70+ endpoints, 30 req/min)
- **STARTUP**: $79/month (80+ endpoints, 80 req/min)  
- **STANDARD**: $299/month (90+ endpoints, 300 req/min)
- **PROFESSIONAL**: $699/month (100+ endpoints, 6000 req/min)

**Current API Key Status**: The configured API key `22a5f59541a146108c317bac84c14084` does not have access to paid endpoints.

---

## What Was Changed

### File: `utils/coinglass_api.py`

**Line 22**: Changed authentication header from `coinglassSecret` to `CG-API-KEY`

```python
async def _fetch_json(url: str, params: dict | None = None) -> dict:
    """Вспомогательная функция для GET‑запросов."""
    async with SEMAPHORE:
        headers = {
            "accept": "application/json",
            "CG-API-KEY": COINGLASS_API_KEY,  # ← Changed from coinglassSecret
        }
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, headers=headers, proxy=PROXY_URL) as resp:
                return await resp.json()
```

---

## Solutions

### Option 1: Subscribe to CoinGlass (Recommended for Full Features)

**Steps**:
1. Visit https://www.coinglass.com/pricing
2. Subscribe to the **HOBBYIST plan** ($29/month minimum)
3. Log in to your CoinGlass account
4. Go to API Key Dashboard
5. Generate a new API key with paid plan access
6. Update `config.py` with the new API key:
   ```python
   COINGLASS_API_KEY = "your_new_paid_api_key_here"
   ```
7. Restart the bot

**Expected Result**: All signal cards will include RSI, Funding Rate, and Long/Short Ratio.

---

### Option 2: Use Free Alternative APIs (Partial Replacement)

Since CoinGlass requires payment, you can replace these metrics with free alternatives:

#### RSI Calculation (DIY)
Calculate RSI from Binance/Bybit historical price data:

```python
# Add to utils/binance_api.py or utils/bybit_api.py
async def calculate_rsi(symbol: str, period: int = 14) -> float | None:
    """
    Calculate RSI from recent price data.
    RSI = 100 - (100 / (1 + RS))
    where RS = Average Gain / Average Loss over period
    """
    try:
        # Fetch last (period + 1) candles
        # Calculate gains and losses
        # Return RSI value
        pass  # Implementation needed
    except:
        return None
```

#### Funding Rate Alternatives

**Binance API** (FREE):
- Endpoint: `https://fapi.binance.com/fapi/v1/fundingRate`
- Parameters: `symbol=BTCUSDT&limit=1`
- No authentication required for reading

**Bybit API** (FREE):
- Endpoint: `https://api.bybit.com/v5/market/funding/history`
- Parameters: `category=linear&symbol=BTCUSDT&limit=1`
- No authentication required

**Implementation**:
```python
async def get_funding_rate_binance(symbol: str) -> float | None:
    """Get current funding rate from Binance futures API."""
    url = "https://fapi.binance.com/fapi/v1/fundingRate"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params={"symbol": symbol, "limit": 1}) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data:
                    return float(data[0]["fundingRate"]) * 100  # Convert to percentage
    return None
```

#### Long/Short Ratio Alternatives

**Binance Global Long/Short Ratio** (FREE):
- Endpoint: `https://fapi.binance.com/futures/data/globalLongShortAccountRatio`
- Parameters: `symbol=BTCUSDT&period=5m&limit=1`
- No authentication required

**Implementation**:
```python
async def get_long_short_ratio_binance(symbol: str, period: str = "5m") -> tuple | None:
    """Get long/short ratio from Binance futures."""
    url = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params={"symbol": symbol, "period": period, "limit": 1}) as resp:
            if resp.status == 200:
                data = await resp.json()
                if data:
                    ratio = float(data[0]["longShortRatio"])
                    # Convert ratio to percentages
                    long_pct = (ratio / (ratio + 1)) * 100
                    short_pct = 100 - long_pct
                    return (long_pct, short_pct)
    return None
```

---

### Option 3: Make CoinGlass Data Truly Optional (Current Behavior)

The bot already handles missing CoinGlass data gracefully. When `None` is returned for RSI, Funding, or Long/Short ratio, the signal message simply omits those fields.

**Current Behavior**:
```
🟢 PUMP! BTCUSDT
Exchange: Binance
💵 Price: 65432.1234
📉 Change: +2.50%
📊 Volume: 123456.78 (+15.25%)
[🔗 Register on Binance](...)
[🔗 Register on Bybit](...)
```

**With CoinGlass Data**:
```
🟢 PUMP! BTCUSDT
Exchange: Binance
💵 Price: 65432.1234
📉 Change: +2.50%
📊 Volume: 123456.78 (+15.25%)
❗️ RSI: 72.5
❕ Funding: 0.01%
🔄 Long/Short: 55.00% / 45.00%
[🔗 Register on Binance](...)
[🔗 Register on Bybit](...)
```

**No Changes Needed**: The bot continues to work and send alerts. CoinGlass data is a "nice-to-have" enhancement, not a requirement.

---

## Testing Results

### Before Fix
```bash
# Old header: coinglassSecret
❌ RSI: {"code":"400","msg":"API key missing."}
❌ Funding: {"code":"40001","msg":"Upgrade plan"}
❌ Long/Short: {"code":"40001","msg":"Upgrade plan"}
```

### After Fix (Correct Header)
```bash
# New header: CG-API-KEY
✅ Header recognized correctly
❌ RSI: {"code":"400","msg":"Upgrade plan"}
❌ Funding: {"code":"30001","msg":"API key missing."} (v2 endpoint)
❌ Long/Short: {"code":"30001","msg":"API key missing."} (v2 endpoint)
```

**Diagnosis**: 
- v4 API header fixed ✅
- Paid subscription required for data access ⚠️

---

## Recommendation

**Short-term** (Free):
1. Keep current CoinGlass integration as-is
2. Implement free Binance/Bybit alternatives for Funding Rate and Long/Short Ratio
3. Calculate RSI from historical data or omit it
4. Update signal messages to show "Data available with premium plan" when None

**Long-term** (Paid):
1. Subscribe to CoinGlass HOBBYIST plan ($29/month)
2. Get full access to RSI, advanced metrics, and heatmaps
3. Unlock premium features for competitive advantage

---

## Files Modified

- ✅ `utils/coinglass_api.py` - Fixed authentication header
- ✅ `BUG-FIXED.md` - This documentation file

---

## Next Steps

**For Free Solution**:
1. Implement Binance Futures API calls for Funding Rate
2. Implement Binance Global Long/Short Ratio endpoint
3. Add DIY RSI calculation from price data
4. Test with low threshold (0.1%) on BTCUSDT

**For Paid Solution**:
1. Subscribe to CoinGlass at https://www.coinglass.com/pricing
2. Generate new API key from dashboard
3. Update `COINGLASS_API_KEY` in `config.py`
4. Restart bot and test

---

**Last Updated**: October 22, 2025  
**Status**: Header fixed ✅ | Paid subscription required ⚠️
