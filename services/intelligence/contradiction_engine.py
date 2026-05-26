"""
Contradiction Engine — rule-based context conflict analysis.

Input : AssetContext (from asset_context.py)
Output: ContradictionResult — supporting / weakening / contradictions + balance

No signals, no predictions, no AI.
Every rule is an explicit condition with a human-readable explanation.

Adaptive weighting (optional):
  analyze_context() accepts an optional `weights` dict ({rule_key: float}).
  When provided, balance scoring uses weighted sums instead of raw counts.
  When absent or all weights are 1.0, behavior is identical to unweighted version.
  Rule keys are defined in rule_weight_engine.SUPPORTING_RULE_KEYS / CONTRADICTION_RULE_KEYS.
"""

from typing import TypedDict
from utils.logger import logger

from services.intelligence.asset_context import AssetContext

# Threshold for balance scoring — identical meaning to the integer thresholds
# used before weighting: a score of 2.0 means "two rules of neutral weight fired"
_ALIGNED_THRESHOLD     = 2.0
_CONFLICTED_THRESHOLD  = 2.0


class ContradictionResult(TypedDict):
    symbol: str
    supporting_factors: list[str]   # signals that reinforce a coherent picture
    weakening_factors: list[str]    # single signals that reduce overall confidence
    contradictions: list[str]       # pairs of signals that conflict with each other
    overall_context_balance: str    # aligned / mixed / conflicted / weak


def analyze_context(
    ctx: AssetContext,
    weights: dict[str, float] | None = None,
) -> ContradictionResult:
    """
    Analyze asset context and return contradiction result.

    weights : optional {rule_key: float} from rule_weight_engine.load_active_weights().
              Defaults to None → all weights treated as 1.0 → identical to prior behavior.
    """
    sym   = ctx["symbol"]
    stt   = ctx["short_term_trend"]   # bullish / neutral / bearish
    htf   = ctx["higher_tf_trend"]    # bullish / neutral / bearish
    rsi   = ctx["rsi_state"]          # overbought / strengthening / neutral / weakening / oversold / unknown
    vol   = ctx["volume_condition"]   # high / average / low
    vola  = ctx["volatility_regime"]  # expanding / normal / contracting
    mom   = ctx["momentum"]           # accelerating / flat / decelerating

    w = weights or {}

    supporting:    list[str] = []
    weakening:     list[str] = []
    contradictions: list[str] = []

    # Weighted scores — each fired rule contributes its weight (default 1.0)
    support_score:      float = 0.0
    contradiction_score: float = 0.0

    # ── Supporting factors ─────────────────────────────────────────────────────

    if stt == "bullish" and htf == "bullish":
        supporting.append("Kısa ve uzun vadeli trend hizalanmış — yükseliş yönünde")
        support_score += w.get("s_stt_bull__htf_bull", 1.0)

    if stt == "bearish" and htf == "bearish":
        supporting.append("Kısa ve uzun vadeli trend hizalanmış — düşüş yönünde")
        support_score += w.get("s_stt_bear__htf_bear", 1.0)

    if rsi == "oversold" and mom == "decelerating":
        supporting.append("RSI aşırı satış bölgesinde ve düşüş devam ediyor — satıcı tükenmesi oluşuyor")
        support_score += w.get("s_rsi_oversold__mom_decel", 1.0)

    if rsi == "overbought" and mom == "accelerating":
        supporting.append("RSI aşırı alım bölgesinde ve fiyat ivmeleniyor — güçlü alıcı baskısı")
        support_score += w.get("s_rsi_overbought__mom_accel", 1.0)

    if rsi in ("strengthening", "overbought") and stt == "bullish":
        supporting.append("RSI güçlenmesi ile kısa vadeli yükseliş trendi örtüşüyor — alıcı baskısı tutarlı")
        support_score += w.get("s_rsi_strength__stt_bull", 1.0)

    if rsi in ("weakening", "oversold") and stt == "bearish":
        supporting.append("RSI zayıflaması ile kısa vadeli düşüş trendi örtüşüyor — satıcı baskısı tutarlı")
        support_score += w.get("s_rsi_weak__stt_bear", 1.0)

    if vol == "high" and mom in ("accelerating", "decelerating"):
        supporting.append("Yüksek hacim güçlü fiyat hareketiyle eşleşiyor — hareket onaylanmış görünüyor")
        support_score += w.get("s_vol_high__mom_strong", 1.0)

    if vola == "expanding" and mom in ("accelerating", "decelerating"):
        supporting.append("Volatilite artışı güçlü fiyat hareketiyle birlikte — hareket ivme kazanıyor")
        support_score += w.get("s_vola_expand__mom_strong", 1.0)

    # ── Weakening factors ──────────────────────────────────────────────────────
    # Direction-neutral single signals — not weighted (no directional claim to evaluate).

    if vol == "low":
        weakening.append("Hacim düşük — fiyat hareketinin güvenilirliği azalıyor")

    if mom == "flat":
        weakening.append("Momentum yatay — net bir yön baskısı okunmuyor")

    if rsi == "neutral":
        weakening.append("RSI nötr bölgede — belirgin bir alıcı veya satıcı baskısı yok")

    if vola == "contracting":
        weakening.append("Volatilite daralıyor — piyasa aktivitesi ve ilgisi azalmış")

    if rsi == "unknown":
        weakening.append("RSI verisi alınamadı — teknik tablo eksik")

    if stt == "neutral" and htf == "neutral":
        weakening.append("Her iki zaman diliminde de net trend yok — piyasa kararsız")

    # ── Contradictions ─────────────────────────────────────────────────────────

    if rsi == "oversold" and htf == "bearish":
        contradictions.append(
            "RSI aşırı satış sinyali veriyor, ancak yüksek zaman dilimi hâlâ düşüş trendinde "
            "— yerel toparlanma mümkün, ancak makro baskı sürebilir"
        )
        contradiction_score += w.get("c_rsi_oversold__htf_bear", 1.0)

    if rsi == "overbought" and mom == "decelerating":
        contradictions.append(
            "RSI aşırı alım bölgesinde ancak momentum yavaşlıyor — tepe oluşumu riski"
        )
        contradiction_score += w.get("c_rsi_overbought__mom_decel", 1.0)

    if stt == "bullish" and htf == "bearish":
        contradictions.append(
            "Kısa vadeli görünüm yükseliş, ancak yüksek zaman dilimi düşüş trendinde "
            "— trend karşıtı hareket olabilir"
        )
        contradiction_score += w.get("c_stt_bull__htf_bear", 1.0)

    if stt == "bearish" and htf == "bullish":
        contradictions.append(
            "Kısa vadeli görünüm düşüş, ancak yüksek zaman dilimi yükseliş trendinde "
            "— geri çekilme mi, trend kırılması mı belirsiz"
        )
        contradiction_score += w.get("c_stt_bear__htf_bull", 1.0)

    if vol == "high" and mom == "flat":
        contradictions.append(
            "Yüksek hacim var ancak fiyat hareketi yatay "
            "— birikim veya dağıtım bölgesi olabilir, yön belirsiz"
        )
        contradiction_score += w.get("c_vol_high__mom_flat", 1.0)

    if vol == "low" and mom in ("accelerating", "decelerating"):
        contradictions.append(
            "Güçlü fiyat hareketi var ancak hacim düşük — hareketin sürdürülebilirliği sorgulanabilir"
        )
        contradiction_score += w.get("c_vol_low__mom_strong", 1.0)

    if rsi == "strengthening" and stt == "bearish":
        contradictions.append(
            "RSI güçleniyor ancak fiyat SMA altında — olası boğa ıraksama sinyali"
        )
        contradiction_score += w.get("c_rsi_strength__stt_bear", 1.0)

    if rsi == "weakening" and stt == "bullish":
        contradictions.append(
            "RSI zayıflıyor ancak fiyat SMA üstünde — olası ayı ıraksama sinyali, momentum kaybı riski"
        )
        contradiction_score += w.get("c_rsi_weak__stt_bull", 1.0)

    if vola == "expanding" and mom == "flat":
        contradictions.append(
            "Volatilite artıyor ancak fiyat hareketi yatay — kırılma baskısı birikebilir, yön henüz belirsiz"
        )
        contradiction_score += w.get("c_vola_expand__mom_flat", 1.0)

    if rsi == "oversold" and stt == "bullish":
        contradictions.append(
            "Fiyat kısa vadeli yükseliş trendinde ancak RSI hâlâ aşırı satış bölgesinde "
            "— toparlanma başlamış olabilir ancak henüz teyit yok"
        )
        contradiction_score += w.get("c_rsi_oversold__stt_bull", 1.0)

    # ── Overall context balance ────────────────────────────────────────────────

    overall_context_balance = _compute_balance(
        support_score, contradiction_score, len(weakening)
    )

    result: ContradictionResult = {
        "symbol": sym,
        "supporting_factors": supporting,
        "weakening_factors": weakening,
        "contradictions": contradictions,
        "overall_context_balance": overall_context_balance,
    }

    weighted = weights is not None
    logger.info(
        f"[ENGINE] {sym}: balance={overall_context_balance} "
        f"support_score={support_score:.2f} "
        f"contradiction_score={contradiction_score:.2f} "
        f"weakening={len(weakening)} "
        f"weighted={'yes' if weighted else 'no'}"
    )
    return result


def _compute_balance(
    support_score: float,
    contradiction_score: float,
    weakening_count: int,
) -> str:
    """
    Weighted balance label.

    Thresholds are numerically identical to the original integer counts when all
    weights are 1.0, preserving backward compatibility exactly:
      conflicted : contradiction_score >= 2.0  (was: len(contradictions) >= 2)
      aligned    : support_score >= 2.0, no contradiction, at most 1 weakening
      weak       : support_score < 0.5, weakening >= 2, no contradiction
      mixed      : everything else
    """
    if contradiction_score >= _CONFLICTED_THRESHOLD:
        return "conflicted"
    if support_score >= _ALIGNED_THRESHOLD and contradiction_score < 0.5 and weakening_count <= 1:
        return "aligned"
    if support_score < 0.5 and weakening_count >= 2 and contradiction_score < 0.5:
        return "weak"
    return "mixed"
