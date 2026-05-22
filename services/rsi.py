from utils.http import get as http_get
from utils.logger import logger
from utils import normalize_symbol

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"


async def get_rsi(symbol: str, period: int = 14) -> float | None:
    binance_symbol = normalize_symbol(symbol)
    if binance_symbol is None:
        logger.warning(f"get_rsi: geçersiz sembol atlandı, symbol={symbol}")
        return None
    data = await http_get(BINANCE_KLINE_URL, params={
        "symbol": binance_symbol,
        "interval": "1h",
        "limit": period + 1,
    })
    if data is None or not isinstance(data, list):
        logger.warning(f"[BINANCE] get_rsi başarısız: symbol={binance_symbol} yanıt={data}")
        return None
    if len(data) < period + 1:
        logger.warning(f"[BINANCE] get_rsi: yetersiz mum verisi, symbol={binance_symbol} adet={len(data)}")
        return None

    # Binance klines artan sırada gelir; index 4 kapanış fiyatıdır
    closes = [float(c[4]) for c in data]
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]

    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]

    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = round(100 - (100 / (1 + rs)), 1)
    logger.info(f"[BINANCE] get_rsi OK: {binance_symbol} RSI={rsi}")
    return rsi
