import time
import statistics
from typing import TypedDict

from utils.http import get as http_get
from utils.logger import logger
from utils import normalize_symbol

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"

# 5-minute per-symbol cache — scheduler runs every 60s; context doesn't need sub-minute freshness
CACHE_TTL = 300


# ── Data structures ────────────────────────────────────────────────────────────

class RawIndicators(TypedDict):
    price: float
    rsi_1h: float | None
    sma20_1h: float
    price_vs_sma20_1h_pct: float   # positive = above SMA (bullish bias)
    sma20_4h: float
    price_vs_sma20_4h_pct: float
    volume_ratio_1h: float          # last closed candle / 20-bar average
    volatility_stdev_pct: float     # stdev of hourly % returns (last 20 closed)
    momentum_5bar_pct: float        # % change across last 5 closed 1h candles


class AssetContext(TypedDict):
    symbol: str
    short_term_trend: str    # bullish / neutral / bearish   (1h SMA20)
    higher_tf_trend: str     # bullish / neutral / bearish   (4h SMA20)
    volatility_regime: str   # expanding / normal / contracting
    volume_condition: str    # high / average / low
    rsi_state: str           # overbought / strengthening / neutral / weakening / oversold
    momentum: str            # accelerating / flat / decelerating
    raw: RawIndicators
    fetched_at: float


# ── Module-level cache ─────────────────────────────────────────────────────────

_cache: dict[str, tuple[float, AssetContext]] = {}


# ── Internal helpers ───────────────────────────────────────────────────────────

async def _fetch_klines(symbol: str, interval: str, limit: int) -> list | None:
    data = await http_get(BINANCE_KLINE_URL, params={
        "symbol": symbol,
        "interval": interval,
        "limit": limit,
    })
    if data is None or not isinstance(data, list):
        logger.warning(f"[CONTEXT] kline başarısız: {symbol} {interval}")
        return None
    if len(data) < limit:
        logger.warning(
            f"[CONTEXT] kline yetersiz: {symbol} {interval} "
            f"beklenen={limit} gelen={len(data)}"
        )
        return None
    return data


def _sma(values: list[float]) -> float:
    return sum(values) / len(values)


def _rsi(closes: list[float], period: int = 14) -> float | None:
    if len(closes) < period + 1:
        return None
    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [c for c in changes if c > 0]
    losses = [-c for c in changes if c < 0]
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100.0
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 1)


# ── Classification functions ───────────────────────────────────────────────────
# Each function takes a single raw number and returns a human-readable label.
# Thresholds are intentionally conservative to avoid false signals.

def _classify_trend(price_vs_sma_pct: float) -> str:
    if price_vs_sma_pct > 0.5:
        return "bullish"
    if price_vs_sma_pct < -0.5:
        return "bearish"
    return "neutral"


def _classify_rsi(rsi: float | None) -> str:
    if rsi is None:
        return "unknown"
    if rsi > 70:
        return "overbought"
    if rsi > 55:
        return "strengthening"
    if rsi >= 45:
        return "neutral"
    if rsi >= 30:
        return "weakening"
    return "oversold"


def _classify_volume(ratio: float) -> str:
    if ratio > 1.5:
        return "high"
    if ratio < 0.5:
        return "low"
    return "average"


def _classify_volatility(stdev_pct: float) -> str:
    if stdev_pct > 1.5:
        return "expanding"
    if stdev_pct < 0.4:
        return "contracting"
    return "normal"


def _classify_momentum(pct: float) -> str:
    if pct > 2.0:
        return "accelerating"
    if pct < -2.0:
        return "decelerating"
    return "flat"


# ── Public API ─────────────────────────────────────────────────────────────────

async def get_asset_context(symbol: str) -> AssetContext | None:
    binance_symbol = normalize_symbol(symbol)
    if binance_symbol is None:
        logger.warning(f"[CONTEXT] geçersiz sembol: {symbol}")
        return None

    now = time.time()
    cached = _cache.get(binance_symbol)
    if cached is not None and (now - cached[0]) < CACHE_TTL:
        return cached[1]

    # Two API calls: 1h × 30 candles, 4h × 22 candles
    klines_1h = await _fetch_klines(binance_symbol, "1h", 30)
    klines_4h = await _fetch_klines(binance_symbol, "4h", 22)
    if klines_1h is None or klines_4h is None:
        return None

    # Binance kline format: [open_time, open, high, low, close, volume, ...]
    closes_1h = [float(c[4]) for c in klines_1h]
    volumes_1h = [float(c[5]) for c in klines_1h]
    closes_4h = [float(c[4]) for c in klines_4h]

    # [-1] may be a still-forming candle; use [-2] for completed-candle calculations
    price = closes_1h[-1]

    sma20_1h = _sma(closes_1h[-21:-1])          # 20 fully closed 1h candles
    sma20_4h = _sma(closes_4h[-21:-1])          # 20 fully closed 4h candles
    price_vs_sma20_1h_pct = (price - sma20_1h) / sma20_1h * 100
    price_vs_sma20_4h_pct = (closes_4h[-2] - sma20_4h) / sma20_4h * 100

    rsi = _rsi(closes_1h[-16:-1])               # 15 fully closed → RSI(14)

    vol_avg = _sma(volumes_1h[-22:-2])           # 20 candles before last closed
    vol_last = volumes_1h[-2]                    # last fully closed candle
    volume_ratio = vol_last / vol_avg if vol_avg > 0 else 1.0

    returns = [
        (closes_1h[i] - closes_1h[i - 1]) / closes_1h[i - 1] * 100
        for i in range(-20, 0)
    ]
    volatility_stdev_pct = round(statistics.stdev(returns), 3)

    momentum_5bar_pct = round(
        (closes_1h[-2] - closes_1h[-7]) / closes_1h[-7] * 100, 2
    )

    raw: RawIndicators = {
        "price": price,
        "rsi_1h": rsi,
        "sma20_1h": round(sma20_1h, 4),
        "price_vs_sma20_1h_pct": round(price_vs_sma20_1h_pct, 2),
        "sma20_4h": round(sma20_4h, 4),
        "price_vs_sma20_4h_pct": round(price_vs_sma20_4h_pct, 2),
        "volume_ratio_1h": round(volume_ratio, 2),
        "volatility_stdev_pct": volatility_stdev_pct,
        "momentum_5bar_pct": momentum_5bar_pct,
    }

    context: AssetContext = {
        "symbol": binance_symbol,
        "short_term_trend": _classify_trend(price_vs_sma20_1h_pct),
        "higher_tf_trend": _classify_trend(price_vs_sma20_4h_pct),
        "volatility_regime": _classify_volatility(volatility_stdev_pct),
        "volume_condition": _classify_volume(volume_ratio),
        "rsi_state": _classify_rsi(rsi),
        "momentum": _classify_momentum(momentum_5bar_pct),
        "raw": raw,
        "fetched_at": now,
    }

    _cache[binance_symbol] = (now, context)
    logger.info(
        f"[CONTEXT] {binance_symbol}: "
        f"trend_1h={context['short_term_trend']} "
        f"trend_4h={context['higher_tf_trend']} "
        f"rsi={rsi} ({context['rsi_state']}) "
        f"vol={context['volume_condition']} "
        f"momentum={context['momentum']}"
    )
    return context
