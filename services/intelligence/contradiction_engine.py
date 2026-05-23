"""
Contradiction Engine — rule-based context conflict analysis.

Input : AssetContext (from asset_context.py)
Output: ContradictionResult — supporting / weakening / contradictions + balance

No signals, no predictions, no AI.
Every rule is an explicit condition with a human-readable explanation.
"""

from typing import TypedDict
from utils.logger import logger

from services.intelligence.asset_context import AssetContext


class ContradictionResult(TypedDict):
    symbol: str
    supporting_factors: list[str]   # signals that reinforce a coherent picture
    weakening_factors: list[str]    # single signals that reduce overall confidence
    contradictions: list[str]       # pairs of signals that conflict with each other
    overall_context_balance: str    # aligned / mixed / conflicted / weak


def analyze_context(ctx: AssetContext) -> ContradictionResult:
    sym   = ctx["symbol"]
    stt   = ctx["short_term_trend"]   # bullish / neutral / bearish
    htf   = ctx["higher_tf_trend"]    # bullish / neutral / bearish
    rsi   = ctx["rsi_state"]          # overbought / strengthening / neutral / weakening / oversold / unknown
    vol   = ctx["volume_condition"]   # high / average / low
    vola  = ctx["volatility_regime"]  # expanding / normal / contracting
    mom   = ctx["momentum"]           # accelerating / flat / decelerating

    supporting: list[str] = []
    weakening:  list[str] = []
    contradictions: list[str] = []

    # ── Supporting factors ─────────────────────────────────────────────────────
    # Two or more signals consistently pointing in the same direction.

    if stt == "bullish" and htf == "bullish":
        supporting.append(
            "Kısa ve uzun vadeli trend hizalanmış — yükseliş yönünde"
        )

    if stt == "bearish" and htf == "bearish":
        supporting.append(
            "Kısa ve uzun vadeli trend hizalanmış — düşüş yönünde"
        )

    if rsi == "oversold" and mom == "decelerating":
        supporting.append(
            "RSI aşırı satış bölgesinde ve düşüş devam ediyor — satıcı tükenmesi oluşuyor"
        )

    if rsi == "overbought" and mom == "accelerating":
        supporting.append(
            "RSI aşırı alım bölgesinde ve fiyat ivmeleniyor — güçlü alıcı baskısı"
        )

    if rsi in ("strengthening", "overbought") and stt == "bullish":
        supporting.append(
            "RSI güçlenmesi ile kısa vadeli yükseliş trendi örtüşüyor — alıcı baskısı tutarlı"
        )

    if rsi in ("weakening", "oversold") and stt == "bearish":
        supporting.append(
            "RSI zayıflaması ile kısa vadeli düşüş trendi örtüşüyor — satıcı baskısı tutarlı"
        )

    if vol == "high" and mom in ("accelerating", "decelerating"):
        supporting.append(
            "Yüksek hacim güçlü fiyat hareketiyle eşleşiyor — hareket onaylanmış görünüyor"
        )

    if vola == "expanding" and mom in ("accelerating", "decelerating"):
        supporting.append(
            "Volatilite artışı güçlü fiyat hareketiyle birlikte — hareket ivme kazanıyor"
        )

    # ── Weakening factors ──────────────────────────────────────────────────────
    # Single signals that independently reduce confidence in any interpretation.

    if vol == "low":
        weakening.append(
            "Hacim düşük — fiyat hareketinin güvenilirliği azalıyor"
        )

    if mom == "flat":
        weakening.append(
            "Momentum yatay — net bir yön baskısı okunmuyor"
        )

    if rsi == "neutral":
        weakening.append(
            "RSI nötr bölgede — belirgin bir alıcı veya satıcı baskısı yok"
        )

    if vola == "contracting":
        weakening.append(
            "Volatilite daralıyor — piyasa aktivitesi ve ilgisi azalmış"
        )

    if rsi == "unknown":
        weakening.append(
            "RSI verisi alınamadı — teknik tablo eksik"
        )

    if stt == "neutral" and htf == "neutral":
        weakening.append(
            "Her iki zaman diliminde de net trend yok — piyasa kararsız"
        )

    # ── Contradictions ─────────────────────────────────────────────────────────
    # Pairs of signals that conflict with each other, reducing interpretation clarity.
    # Each contradiction is a specific (A AND B) condition.

    if rsi == "oversold" and htf == "bearish":
        contradictions.append(
            "RSI aşırı satış sinyali veriyor, ancak yüksek zaman dilimi hâlâ düşüş trendinde "
            "— yerel toparlanma mümkün, ancak makro baskı sürebilir"
        )

    if rsi == "overbought" and mom == "decelerating":
        contradictions.append(
            "RSI aşırı alım bölgesinde ancak momentum yavaşlıyor "
            "— tepe oluşumu riski"
        )

    if stt == "bullish" and htf == "bearish":
        contradictions.append(
            "Kısa vadeli görünüm yükseliş, ancak yüksek zaman dilimi düşüş trendinde "
            "— trend karşıtı hareket olabilir"
        )

    if stt == "bearish" and htf == "bullish":
        contradictions.append(
            "Kısa vadeli görünüm düşüş, ancak yüksek zaman dilimi yükseliş trendinde "
            "— geri çekilme mi, trend kırılması mı belirsiz"
        )

    if vol == "high" and mom == "flat":
        contradictions.append(
            "Yüksek hacim var ancak fiyat hareketi yatay "
            "— birikim veya dağıtım bölgesi olabilir, yön belirsiz"
        )

    if vol == "low" and mom in ("accelerating", "decelerating"):
        contradictions.append(
            "Güçlü fiyat hareketi var ancak hacim düşük "
            "— hareketin sürdürülebilirliği sorgulanabilir"
        )

    if rsi == "strengthening" and stt == "bearish":
        contradictions.append(
            "RSI güçleniyor ancak fiyat SMA altında "
            "— olası boğa ıraksama sinyali"
        )

    if rsi == "weakening" and stt == "bullish":
        contradictions.append(
            "RSI zayıflıyor ancak fiyat SMA üstünde "
            "— olası ayı ıraksama sinyali, momentum kaybı riski"
        )

    if vola == "expanding" and mom == "flat":
        contradictions.append(
            "Volatilite artıyor ancak fiyat hareketi yatay "
            "— kırılma baskısı birikebilir, yön henüz belirsiz"
        )

    if rsi == "oversold" and stt == "bullish":
        contradictions.append(
            "Fiyat kısa vadeli yükseliş trendinde ancak RSI hâlâ aşırı satış bölgesinde "
            "— toparlanma başlamış olabilir ancak henüz teyit yok"
        )

    # ── Overall context balance ────────────────────────────────────────────────

    overall_context_balance = _compute_balance(supporting, weakening, contradictions)

    result: ContradictionResult = {
        "symbol": sym,
        "supporting_factors": supporting,
        "weakening_factors": weakening,
        "contradictions": contradictions,
        "overall_context_balance": overall_context_balance,
    }

    logger.info(
        f"[ENGINE] {sym}: balance={overall_context_balance} "
        f"supporting={len(supporting)} "
        f"weakening={len(weakening)} "
        f"contradictions={len(contradictions)}"
    )
    return result


def _compute_balance(
    supporting: list[str],
    weakening: list[str],
    contradictions: list[str],
) -> str:
    """
    Deterministic balance label derived from rule counts.

    aligned    — multiple supporting signals, no contradictions, at most one weakening
    conflicted — two or more contradictions found
    weak       — no supporting signals, two or more weakening signals
    mixed      — everything else
    """
    if len(contradictions) >= 2:
        return "conflicted"
    if len(supporting) >= 2 and len(contradictions) == 0 and len(weakening) <= 1:
        return "aligned"
    if len(supporting) == 0 and len(weakening) >= 2 and len(contradictions) == 0:
        return "weak"
    return "mixed"
