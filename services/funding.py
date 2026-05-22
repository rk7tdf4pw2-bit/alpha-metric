from utils.http import get as http_get
from utils.logger import logger

BYBIT_TICKER_URL = "https://api.bybit.com/v5/market/tickers"


async def get_funding_rate(symbol: str = "BTC") -> float | None:
    data = await http_get(BYBIT_TICKER_URL, params={
        "category": "linear",
        "symbol": f"{symbol.upper()}USDT",
    })
    if data is None or data.get("retCode") != 0:
        logger.warning(f"get_funding_rate başarısız: symbol={symbol} yanıt={data}")
        return None
    items = data.get("result", {}).get("list", [])
    if not items:
        return None
    rate = items[0].get("fundingRate")
    if rate is None:
        return None
    return float(rate)
