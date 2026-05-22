from utils.http import get as http_get
from utils.logger import logger
from utils import normalize_symbol

BINANCE_FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"


async def get_funding_rate(symbol: str = "BTC") -> float | None:
    binance_symbol = normalize_symbol(symbol)
    if binance_symbol is None:
        logger.warning(f"get_funding_rate: geçersiz sembol atlandı, symbol={symbol}")
        return None
    data = await http_get(BINANCE_FUNDING_URL, params={"symbol": binance_symbol})
    if data is None or "lastFundingRate" not in data:
        logger.warning(f"[BINANCE] get_funding_rate başarısız: symbol={binance_symbol} yanıt={data}")
        return None
    rate = float(data["lastFundingRate"])
    logger.info(f"[BINANCE] get_funding_rate OK: {binance_symbol} rate={rate:.6f}")
    return rate
