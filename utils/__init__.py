def normalize_symbol(symbol: str) -> str | None:
    """BTC→BTCUSDT, BTCUSDT→BTCUSDT, USDT→None (USDTUSDT oluşmasını önler)."""
    s = symbol.upper().strip()
    base = s[:-4] if s.endswith("USDT") else s
    if not base:
        return None
    return base + "USDT"
