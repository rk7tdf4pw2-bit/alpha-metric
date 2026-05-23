import time
from typing import TypedDict

from config.settings import CMC_API_KEY
from utils.http import get as http_get
from utils.logger import logger

CMC_GLOBAL_URL = "https://pro-api.coinmarketcap.com/v1/global-metrics/quotes/latest"

# 5-minute cache — CMC free tier allows ~333 calls/day; scheduler runs every 60s
CACHE_TTL = 300


class MarketOverview(TypedDict):
    btc_dominance: float        # BTC as % of total market cap
    total_market_cap_usd: float # total crypto market cap in USD
    total_volume_24h_usd: float # 24h global trading volume in USD
    fetched_at: float           # unix timestamp of last successful fetch


_cache: MarketOverview | None = None
_cache_time: float = 0.0


async def get_market_overview() -> MarketOverview | None:
    global _cache, _cache_time

    if _cache is not None and (time.time() - _cache_time) < CACHE_TTL:
        return _cache

    if not CMC_API_KEY:
        logger.warning("[CMC] CMC_API_KEY tanımlı değil, market_overview atlandı")
        return None

    data = await http_get(
        CMC_GLOBAL_URL,
        headers={"X-CMC_PRO_API_KEY": CMC_API_KEY},
    )

    if data is None or "data" not in data:
        logger.warning(f"[CMC] market_overview başarısız: yanıt={data}")
        return None

    try:
        d = data["data"]
        usd = d["quote"]["USD"]
        result: MarketOverview = {
            "btc_dominance": round(float(d["btc_dominance"]), 2),
            "total_market_cap_usd": float(usd["total_market_cap"]),
            "total_volume_24h_usd": float(usd["total_volume_24h"]),
            "fetched_at": time.time(),
        }
        _cache = result
        _cache_time = result["fetched_at"]
        logger.info(
            f"[CMC] market_overview OK: "
            f"BTC.d={result['btc_dominance']}% "
            f"mcap=${result['total_market_cap_usd'] / 1e12:.2f}T "
            f"vol24h=${result['total_volume_24h_usd'] / 1e9:.1f}B"
        )
        return result
    except (KeyError, TypeError, ValueError) as e:
        logger.error(f"[CMC] market_overview parse hatası: {e}")
        return None
