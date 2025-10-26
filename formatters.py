# utils/formatters.py
def format_signal(
    symbol: str,
    is_pump: bool,
    exchange: str,
    price_now: float,
    price_change: float,
    volume_now: float,
    volume_change: float,
    rsi: float | None = None,
    funding: float | None = None,
    long_short_ratio: tuple | None = None,
    open_interest: float | None = None,
    orderbook_ratio: float | None = None,
) -> str:
    """
    Build the text of a pump/dump signal message.

    This version adds several improvements over the original:

    * The coin symbol becomes a clickable Markdown link pointing to its
      funding-rate page on CoinGlass. If the symbol ends with "USDT",
      the "USDT" suffix is stripped when forming the URL (e.g.,
      CRVUSDT → https://www.coinglass.com/funding/CRV).
    * The exchange line is prefixed with a currency-exchange emoji (💱).
    * The long/short line is renamed to "Long/Short ratio" to clarify
      the meaning of the values.
    * The function retains the ability to include optional RSI, funding
      rate, and long/short ratio values, and appends referral links
      unchanged.

    Parameters
    ----------
    symbol : str
        The trading pair symbol, e.g. "BTCUSDT".
    is_pump : bool
        True if the signal is a pump; False if it's a dump.
    exchange : str
        The name of the exchange (e.g. "Binance" or "Bybit").
    price_now : float
        Current price for the pair.
    price_change : float
        Percentage change over the configured timeframe.
    volume_now : float
        Current traded volume in the timeframe.
    volume_change : float
        Percentage change in volume over the timeframe.
    rsi : float | None, optional
        Relative Strength Index value; include if available.
    funding : float | None, optional
        Funding rate; include if available.
    long_short_ratio : tuple | None, optional
        Tuple of long- and short-position percentages; include if available.

    Returns
    -------
    str
        A Markdown-formatted string ready to be sent via Telegram with
        parse_mode="Markdown". The string contains line breaks and
        clickable hyperlinks where appropriate.
    """
    # Determine trend label based on pump/dump flag.
    trend = "🟢 PUMP" if is_pump else "🔴 DUMP"

    # Prepare a CoinGlass URL for the base symbol. If the trading pair
    # ends with "USDT", strip that suffix; otherwise use the full symbol.
    base_symbol = symbol[:-4] if symbol.endswith("USDT") else symbol
    coinglass_url = f"https://www.coinglass.com/currencies/{base_symbol}"

    # Build the lines of the message. The first line uses a Markdown
    # hyperlink to make the symbol clickable. The exchange line includes
    # an emoji to visually separate it from the rest.
    lines = [
        f"{trend}! [{symbol}]({coinglass_url})",
        f"💱 Exchange: {exchange}",
        f"💵 Price: {price_now:.4f}",
        f"📉 Change: {price_change:+.2f}%",
        f"📊 Volume: {volume_now:.2f} ({volume_change:+.2f}%)",
    ]

    # Optionally append RSI, funding, and long/short ratio information.
    if rsi is not None:
        lines.append(f"❗️ RSI: {rsi}")
    if funding is not None:
        lines.append(f"❕ Funding: {funding}")
    if long_short_ratio is not None:
        long_pct, short_pct = long_short_ratio
        lines.append(f"🔄 Long/Short ratio: {long_pct:.2f}% / {short_pct:.2f}%")
    if open_interest is not None:
        lines.append(f"💰 Open interest: {open_interest:.2f}")
    if orderbook_ratio is not None:
        lines.append(f"📊 Orderbook ratio (bid/ask): {orderbook_ratio:.2f}")

    # Referral links remain unchanged. Replace these URLs with your own
    # referral codes if desired.
    lines.append(
        "[🔗 Register on Binance](https://accounts.binance.com/register?ref=444333168)"
    )
    lines.append(
        "[🔗 Register on Bybit](https://www.bybit.com/invite?ref=3GKKD83)"
    )

    # Join all lines with newlines. The resulting string can be sent
    # directly via Telegram with parse_mode="Markdown".
    return "\n".join(lines)
