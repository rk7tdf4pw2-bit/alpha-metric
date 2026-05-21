from utils.http import get as http_get

KLINES_URL = "https://api.binance.com/api/v3/klines"


async def get_rsi(symbol: str, period: int = 14) -> float | None:
    data = await http_get(KLINES_URL, params={
        "symbol": f"{symbol.upper()}USDT",
        "interval": "1h",
        "limit": period + 1,
    })
    if data is None or isinstance(data, dict):
        return None

    closes = [float(candle[4]) for candle in data]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)
