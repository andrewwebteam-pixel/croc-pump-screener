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
) -> str:
    """
    Формирует текст сообщения о сигнале. Если is_pump = True, помечаем зелёным (🟢), иначе красным (🔴).
    Можем передавать None для необязательных параметров RSI, funding и long/short ratio.
    """
    trend = "🟢 PUMP" if is_pump else "🔴 DUMP"
    lines = [
        f"{trend}! {symbol}",
        f"Exchange: {exchange}",
        f"💵 Price: {price_now:.4f}",
        f"📉 Change: {price_change:+.2f}%",
        f"📊 Volume: {volume_now:.2f} ({volume_change:+.2f}%)",
    ]
    if rsi is not None:
        lines.append(f"❗️ RSI: {rsi}")
    if funding is not None:
        lines.append(f"❕ Funding: {funding}")
    if long_short_ratio is not None:
        long_pct, short_pct = long_short_ratio
        lines.append(f"🔄 Long/Short: {long_pct:.2f}% / {short_pct:.2f}%")
    # Добавьте свои реферальные ссылки здесь (замените на свои URL)
    lines.append("🔗 Register on Binance (ref) — your_ref_link")
    lines.append("🔗 Register on Bybit (ref) — your_ref_link")
    return "\n".join(lines)
