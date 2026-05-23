"""
Analysis Schema — unified semantic container for Alpha Metric's reasoning pipeline.

Why this design supports explainable AI:

Each section answers a distinct question in the reasoning chain:

  evidence              → "What does the data actually show?"      (observable facts)
  context               → "How do we classify these states?"        (labeled interpretations)
  supporting_factors    → "Which signals agree with each other?"    (coherent patterns)
  weakening_factors     → "What reduces confidence?"                (isolated doubts)
  contradictions        → "Where do signals conflict?"              (tension points)
  overall_context_balance → "What is the net picture?"             (single-word summary)
  risks                 → "What could invalidate this reading?"     (forward cautions)
  market_overview       → "What is the macro backdrop?"            (global context)

A future AI reasoning layer can process each section independently.
Every output it generates can be traced back to a specific section — never a black box.
This structure also enables evaluation: store schemas over time, compare predictions
against outcomes, and audit where the reasoning chain fails.
"""

import time
from datetime import datetime, timezone
from typing import TypedDict

from services.intelligence.asset_context import AssetContext
from services.intelligence.contradiction_engine import ContradictionResult
from services.intelligence.market_overview import MarketOverview
from utils.logger import logger


# ── Sub-schemas ────────────────────────────────────────────────────────────────

class ContextStates(TypedDict):
    """Classified market states — labels only, no raw numbers."""
    short_term_trend: str    # bullish / neutral / bearish
    higher_tf_trend: str     # bullish / neutral / bearish
    volatility_regime: str   # expanding / normal / contracting
    volume_condition: str    # high / average / low
    rsi_state: str           # overbought / strengthening / neutral / weakening / oversold / unknown
    momentum: str            # accelerating / flat / decelerating


class AnalysisMetadata(TypedDict):
    symbol: str
    generated_at: float      # unix timestamp — for sorting and time-series queries
    generated_at_iso: str    # ISO 8601 — for logs, storage, and human readability
    layers_used: list[str]   # which data layers contributed to this analysis


# ── Main schema ────────────────────────────────────────────────────────────────

class AnalysisSchema(TypedDict):
    metadata: AnalysisMetadata
    evidence: list[str]               # raw observable facts derived from indicators
    context: ContextStates            # classified market states
    supporting_factors: list[str]     # signals that reinforce a coherent picture
    weakening_factors: list[str]      # signals that reduce confidence
    contradictions: list[str]         # conflicting signal pairs
    overall_context_balance: str      # aligned / mixed / conflicted / weak
    risks: list[str]                  # forward-looking cautions derived deterministically
    market_overview: MarketOverview | None  # macro backdrop from CoinMarketCap


# ── Builder ────────────────────────────────────────────────────────────────────

def build_analysis(
    asset_ctx: AssetContext,
    contradiction: ContradictionResult,
    market_overview: MarketOverview | None = None,
) -> AnalysisSchema:
    now = time.time()
    sym = asset_ctx["symbol"]

    layers = ["binance_spot", "binance_klines", "contradiction_engine"]
    if market_overview is not None:
        layers.append("coinmarketcap")

    schema: AnalysisSchema = {
        "metadata": {
            "symbol": sym,
            "generated_at": now,
            "generated_at_iso": datetime.fromtimestamp(now, tz=timezone.utc).isoformat(),
            "layers_used": layers,
        },
        "evidence": _build_evidence(asset_ctx),
        "context": {
            "short_term_trend": asset_ctx["short_term_trend"],
            "higher_tf_trend": asset_ctx["higher_tf_trend"],
            "volatility_regime": asset_ctx["volatility_regime"],
            "volume_condition": asset_ctx["volume_condition"],
            "rsi_state": asset_ctx["rsi_state"],
            "momentum": asset_ctx["momentum"],
        },
        "supporting_factors": contradiction["supporting_factors"],
        "weakening_factors": contradiction["weakening_factors"],
        "contradictions": contradiction["contradictions"],
        "overall_context_balance": contradiction["overall_context_balance"],
        "risks": _build_risks(asset_ctx, contradiction, market_overview),
        "market_overview": market_overview,
    }

    logger.info(
        f"[SCHEMA] {sym}: balance={schema['overall_context_balance']} "
        f"evidence={len(schema['evidence'])} "
        f"risks={len(schema['risks'])} "
        f"layers={layers}"
    )
    return schema


# ── Internal builders ──────────────────────────────────────────────────────────

def _build_evidence(ctx: AssetContext) -> list[str]:
    """Convert raw indicator numbers into human-readable observable facts."""
    raw = ctx["raw"]
    items: list[str] = []

    rsi = raw.get("rsi_1h")
    if rsi is not None:
        items.append(f"RSI(14) 1s: {rsi}")

    vs1h = raw.get("price_vs_sma20_1h_pct", 0.0)
    direction = "üstünde" if vs1h >= 0 else "altında"
    items.append(f"Fiyat, 1s SMA20'nin {abs(vs1h):.2f}% {direction}")

    vs4h = raw.get("price_vs_sma20_4h_pct", 0.0)
    direction = "üstünde" if vs4h >= 0 else "altında"
    items.append(f"Fiyat, 4s SMA20'nin {abs(vs4h):.2f}% {direction}")

    vol = raw.get("volume_ratio_1h", 1.0)
    items.append(f"Hacim: 20-bar ortalamasının {vol:.1f}x'i")

    mom = raw.get("momentum_5bar_pct", 0.0)
    sign = "+" if mom >= 0 else ""
    items.append(f"5 saatlik momentum: {sign}{mom:.2f}%")

    stdev = raw.get("volatility_stdev_pct", 0.0)
    items.append(f"Saatlik volatilite (stdev): {stdev:.3f}%")

    return items


def _build_risks(
    ctx: AssetContext,
    contradiction: ContradictionResult,
    market_overview: MarketOverview | None,
) -> list[str]:
    """
    Derive forward-looking cautions deterministically from context state.
    These are not predictions — they are conditional concerns.
    """
    risks: list[str] = []
    stt   = ctx["short_term_trend"]
    htf   = ctx["higher_tf_trend"]
    rsi   = ctx["rsi_state"]
    vol   = ctx["volume_condition"]
    vola  = ctx["volatility_regime"]
    mom   = ctx["momentum"]
    bal   = contradiction["overall_context_balance"]

    if rsi == "oversold" and htf == "bearish":
        risks.append(
            "Yerel toparlanma makro düşüş trendi tarafından baskılanabilir"
        )

    if stt == "bullish" and htf == "bearish":
        risks.append(
            "Kısa vadeli yükseliş sürdürülebilir olmayabilir — makro trend karşı yönde"
        )

    if rsi == "overbought" and mom == "decelerating":
        risks.append(
            "Aşırı alım bölgesinde yavaşlayan momentum — dönüş riski artmış"
        )

    if rsi == "weakening" and stt == "bullish":
        risks.append(
            "RSI momentum kaybı devam ederse yükseliş trendinin sürdürülebilirliği sorgulanabilir"
        )

    if vol == "low" and stt != "neutral":
        risks.append(
            "Düşük hacim mevcut trendi kırılgan yapıyor"
        )

    if vola == "expanding" and mom == "flat":
        risks.append(
            "Artan volatilite + yatay fiyat: ani yönlü kırılma için baskı birikebilir"
        )

    if bal == "conflicted":
        risks.append(
            "Çelişkili sinyaller — herhangi bir yorumun güven aralığı düşük"
        )

    # BTC dominance risk — only for non-BTC assets when macro context is available
    if (
        market_overview is not None
        and ctx["symbol"] != "BTCUSDT"
        and market_overview["btc_dominance"] > 55.0
    ):
        risks.append(
            f"BTC dominance yüksek ({market_overview['btc_dominance']:.1f}%) "
            "— altcoin toparlanması sınırlı kalabilir"
        )

    return risks
