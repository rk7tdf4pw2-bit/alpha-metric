from utils.http import get as http_get
from utils.logger import logger

BYBIT_TICKER_URL = "https://api.bybit.com/v5/market/tickers"


async def get_price(symbol: str) -> str | None:
    data = await http_get(BYBIT_TICKER_URL, params={
        "category": "spot",
        "symbol": f"{symbol.upper()}USDT",
    })
    if data is None or data.get("retCode") != 0:
        logger.warning(f"get_price başarısız: symbol={symbol} yanıt={data}")
        return None
    items = data.get("result", {}).get("list", [])
    if not items:
        logger.warning(f"get_price: boş liste döndü, symbol={symbol}")
        return None
    return f"${float(items[0]['lastPrice']):,.2f}"
