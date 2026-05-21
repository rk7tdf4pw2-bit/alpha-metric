from utils.http import get as http_get

FUNDING_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"


async def get_funding_rate(symbol: str = "BTC") -> float | None:
    data = await http_get(FUNDING_URL, params={"symbol": f"{symbol.upper()}USDT"})
    if data is None or "lastFundingRate" not in data:
        return None
    return float(data["lastFundingRate"])
