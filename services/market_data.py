from utils.http import get as http_get

BINANCE_URL = "https://api.binance.com/api/v3/ticker/price"


async def get_price(symbol: str) -> str | None:
    data = await http_get(BINANCE_URL, params={"symbol": f"{symbol.upper()}USDT"})
    if data is None or "code" in data:
        return None
    return f"${float(data['price']):,.2f}"
