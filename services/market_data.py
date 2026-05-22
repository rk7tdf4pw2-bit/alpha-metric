from utils.http import get as http_get
from utils.logger import logger
from utils import normalize_symbol

BINANCE_TICKER_URL = "https://api.binance.com/api/v3/ticker/price"


async def get_price(symbol: str) -> str | None:
    binance_symbol = normalize_symbol(symbol)
    if binance_symbol is None:
        logger.warning(f"get_price: geçersiz sembol atlandı, symbol={symbol}")
        return None
    data = await http_get(BINANCE_TICKER_URL, params={"symbol": binance_symbol})
    if data is None or "price" not in data:
        logger.warning(f"[BINANCE] get_price başarısız: symbol={binance_symbol} yanıt={data}")
        return None
    logger.info(f"[BINANCE] get_price OK: {binance_symbol}={data['price']}")
    return f"${float(data['price']):,.2f}"
