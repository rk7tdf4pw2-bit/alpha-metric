from utils.http import get as http_get
from utils.logger import logger

BYBIT_KLINE_URL = "https://api.bybit.com/v5/market/kline"


async def get_rsi(symbol: str, period: int = 14) -> float | None:
    data = await http_get(BYBIT_KLINE_URL, params={
        "category": "spot",
        "symbol": f"{symbol.upper()}USDT",
        "interval": "60",
        "limit": period + 1,
    })
    if data is None or data.get("retCode") != 0:
        logger.warning(f"get_rsi başarısız: symbol={symbol} yanıt={data}")
        return None
    candles = data.get("result", {}).get("list", [])
    if len(candles) < period + 1:
        logger.warning(f"get_rsi: yetersiz mum verisi, symbol={symbol} adet={len(candles)}")
        return None

    candles = list(reversed(candles))
    closes = [float(c[4]) for c in candles]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)
