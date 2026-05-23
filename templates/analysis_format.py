"""
Analysis output formatter for Telegram delivery.

Design philosophy:
  Alpha Metric is NOT a hype bot. Output should read like a calm analyst —
  structured, grounded, and honest about uncertainty.

  Credibility comes from:
    1. Showing WHY a conclusion is reached (schema → interpretation chain)
    2. Naming what is missing or conflicting (weakening factors, contradictions)
    3. Using qualified language (confidence level, not certainty claims)

  Every section has a purpose:
    Piyasa Durumu      → observable state, no interpretation yet
    Destekleyenler     → signals that agree with each other
    Zayıflatanlar      → signals that reduce confidence
    Çelişkiler         → signals that conflict — honesty about tension
    Yorum              → what the signals mean together (AI layer)
    Güven              → how reliable this reading is
    Riskler            → what could invalidate the reading

Message length target: 900–1400 chars — comfortable on mobile.
Telegram hard limit: 4096 chars.
"""

import re
from services.intelligence.analysis_schema import AnalysisSchema
from services.intelligence.reasoning import ReasoningOutput


# ── Balance labels — calm, professional, no caps ───────────────────────────────

_BALANCE_LABEL = {
    "aligned":    "Hizalı ✓",      # multiple signals agree, no contradictions
    "mixed":      "Karma ≈",       # some agreement, some tension
    "conflicted": "Çelişkili ✗",   # two or more contradictions
    "weak":       "Zayıf –",       # no supporting signals, multiple weakeners
}


# ── Section helpers ────────────────────────────────────────────────────────────

_BOLD_RE = re.compile(r"\*{1,2}([^*]+)\*{1,2}")
# Matches Claude's **Section:** prefix to find the Yorum paragraph
_YORUM_RE = re.compile(r"\*\*Yorum:\*\*\s*(.*?)(?=\*\*Güven:|$)", re.DOTALL)

_MAX_YORUM_CHARS = 550   # cap AI interpretation paragraph length on Telegram


def _strip_markdown(text: str) -> str:
    return _BOLD_RE.sub(r"\1", text).strip()


def _bullet_section(header: str, items: list[str], max_items: int) -> list[str]:
    """Return header + capped bullet list. Returns [] if items is empty."""
    if not items:
        return []
    lines = [header]
    for item in items[:max_items]:
        lines.append(f"• {item}")
    overflow = len(items) - max_items
    if overflow > 0:
        lines.append(f"  (+{overflow} sinyal daha)")
    return lines


def _extract_interpretation(reasoning_out: ReasoningOutput, balance: str) -> str:
    """
    Extract Claude's Yorum paragraph from the response text.
    Falls back to a schema-derived sentence if extraction fails or fallback is active.
    """
    if reasoning_out["fallback_used"]:
        return (
            f"Sinyal dengesi '{balance}' olarak hesaplandı. "
            "Deterministik analiz gösterilmektedir — AI yorumlama katmanına şu an ulaşılamıyor."
        )

    raw = reasoning_out.get("text", "")
    match = _YORUM_RE.search(raw)
    if match:
        yorum = _strip_markdown(match.group(1)).strip()
        if len(yorum) > _MAX_YORUM_CHARS:
            yorum = yorum[:_MAX_YORUM_CHARS].rsplit(" ", 1)[0] + "…"
        return yorum

    # Regex missed — strip full text and truncate as fallback
    stripped = _strip_markdown(raw)
    return stripped[:_MAX_YORUM_CHARS].rsplit(" ", 1)[0] + "…" if len(stripped) > _MAX_YORUM_CHARS else stripped


# ── Main formatter ─────────────────────────────────────────────────────────────

def format_analysis(schema: AnalysisSchema, reasoning_out: ReasoningOutput) -> str:
    """
    Build the complete Telegram message from schema + reasoning output.

    Structure:
      Header (symbol + balance)
      Piyasa Durumu (labeled states — no interpretation)
      Destekleyenler (if any)
      Zayıflatanlar (if any)
      Çelişkiler (if any)
      Yorum (AI interpretation or deterministic fallback)
      Güven
      Riskler (if any)
      Footer (model + timing, or fallback indicator)
    """
    sym = schema["metadata"]["symbol"]
    bal = schema["overall_context_balance"]
    ctx = schema["context"]
    balance_display = _BALANCE_LABEL.get(bal, bal)

    blocks: list[list[str]] = []

    # ── Header ─────────────────────────────────────────────────────────────
    blocks.append([
        f"Alpha Metric — {sym}",
        f"Sinyal Dengesi: {balance_display}",
    ])

    # ── Market state (observable facts only, no interpretation) ────────────
    blocks.append([
        "Piyasa Durumu",
        f"Trend 1s: {ctx['short_term_trend']}  ·  Trend 4s: {ctx['higher_tf_trend']}",
        f"RSI: {ctx['rsi_state']}  ·  Momentum: {ctx['momentum']}",
        f"Hacim: {ctx['volume_condition']}  ·  Volatilite: {ctx['volatility_regime']}",
    ])

    # ── Supporting factors (max 3) ─────────────────────────────────────────
    section = _bullet_section(
        "Destekleyenler", schema["supporting_factors"], max_items=3
    )
    if section:
        blocks.append(section)

    # ── Weakening factors (max 3) ──────────────────────────────────────────
    section = _bullet_section(
        "Zayıflatanlar", schema["weakening_factors"], max_items=3
    )
    if section:
        blocks.append(section)

    # ── Contradictions (max 2 — most impactful) ────────────────────────────
    section = _bullet_section(
        "Çelişkiler", schema["contradictions"], max_items=2
    )
    if section:
        blocks.append(section)

    # ── AI interpretation ──────────────────────────────────────────────────
    interpretation = _extract_interpretation(reasoning_out, bal)
    blocks.append([
        "Yorum",
        interpretation,
    ])

    # ── Confidence ─────────────────────────────────────────────────────────
    blocks.append([f"Güven: {reasoning_out['confidence']}"])

    # ── Risks (max 3) ──────────────────────────────────────────────────────
    section = _bullet_section("Riskler", schema["risks"], max_items=3)
    if section:
        blocks.append(section)

    # ── Footer ─────────────────────────────────────────────────────────────
    if reasoning_out["fallback_used"]:
        footer = "Deterministik özet · AI katmanı devre dışı"
    else:
        secs = reasoning_out["reasoning_ms"] / 1000
        model = reasoning_out["model_used"]
        footer = f"{model}  ·  {secs:.1f}s"

    blocks.append(["─" * 28, footer])

    # Join blocks with blank line between each section
    return "\n\n".join("\n".join(block) for block in blocks)
