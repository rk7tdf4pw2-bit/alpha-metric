"""
Reasoning quality validator — lightweight, deterministic guardrail layer.

Why this layer exists:
  Claude follows instructions well, but no system prompt is perfect.
  This validator acts as a final checkpoint between Claude's output
  and the user — catching the small number of cases where the model
  drifts toward trading advice, false certainty, or low-quality output.

  It does NOT model the meaning of text.
  It does NOT call any external service.
  Every rule is explicit, auditable, and independently testable.

  Trust is built not by assuming Claude is always right,
  but by verifying each output against a known standard.

Severity levels:
  REJECTED  — auto-fallback; violates core safety constraints
  WARNING   — logged and accepted; borderline quality signal
"""

import re
from typing import TypedDict

from utils.logger import logger


# ── Output schema ──────────────────────────────────────────────────────────────

class ValidationResult(TypedDict):
    passed: bool          # True = no rejection (warnings are still OK)
    rejected: bool        # True = must fall back to deterministic output
    rejection_reason: str | None   # which rule triggered rejection
    warnings: list[str]   # list of quality warnings (non-blocking)
    char_count: int        # output length in characters


# ── Length thresholds ──────────────────────────────────────────────────────────
# Too short = Claude failed to generate meaningful content
# Too long  = Claude ignored the "concise" instruction

_MIN_CHARS = 100
_MAX_CHARS = 1600


# ── Rejection rules ────────────────────────────────────────────────────────────
# Any match here → fallback. These are core safety violations.
# Rules use Turkish word boundaries (Python re: \b works with Unicode letters).

_REJECTION_RULES: list[tuple[re.Pattern, str]] = [
    # Trading advice imperatives — urgency + action
    (
        re.compile(r"\b(şimdi|hemen|artık)\s+(al|sat)\b", re.IGNORECASE),
        "İşlem tavsiyesi: aciliyet + al/sat",
    ),
    (
        re.compile(r"\b(al|sat)\s+(şimdi|hemen|artık)\b", re.IGNORECASE),
        "İşlem tavsiyesi: al/sat + aciliyet",
    ),
    # Position opening instructions
    (
        re.compile(r"\b(long|short)\s+(aç|gir)\b", re.IGNORECASE),
        "Pozisyon tavsiyesi: long/short aç",
    ),
    # Direct investment instruction
    (
        re.compile(r"\byatırım\s+yap\b", re.IGNORECASE),
        "Yatırım tavsiyesi",
    ),
    # English trading terms (code-switching)
    (
        re.compile(r"\b(buy|sell)\b", re.IGNORECASE),
        "İngilizce işlem tavsiyesi (buy/sell)",
    ),
    # Guarantee claims — factually false for market predictions
    (
        re.compile(r"\bgaranti(li|siz)?\b", re.IGNORECASE),
        "Garanti ifadesi — piyasalar için geçersiz",
    ),
]


# ── Warning rules ──────────────────────────────────────────────────────────────
# These are flags, not blockers. Logged for audit, output is still accepted.

_WARNING_RULES: list[tuple[re.Pattern, str]] = [
    # Unhedged future-tense direction claims
    (
        re.compile(r"\b(yükselecek|düşecek|artacak|azalacak|kırılacak|ulaşacak)\b", re.IGNORECASE),
        "Kesin gelecek tahmin dili",
    ),
    # Excessive certainty adverbs
    (
        re.compile(r"\b(kesinlikle|mutlaka|hiç\s+şüphesiz)\b", re.IGNORECASE),
        "Aşırı kesinlik ifadesi",
    ),
    (
        re.compile(r"\bkesin\s+olarak\b", re.IGNORECASE),
        "Kesin olmak üzere ifadesi",
    ),
    # Hype-adjacent phrasing
    (
        re.compile(r"\b(fırsat|kaçırmayın|şans|büyük\s+hareket)\b", re.IGNORECASE),
        "Hype dili tespit edildi",
    ),
]

# Required section markers — Claude must include both
_REQUIRED_SECTIONS = ["Yorum", "Güven"]


# ── Repetition detection ───────────────────────────────────────────────────────

_SENTENCE_SPLIT_RE = re.compile(r"[.!?\n]+")
_JACCARD_THRESHOLD = 0.65   # above this → sentences are suspiciously similar


def _jaccard(a: str, b: str) -> float:
    """Word-level Jaccard similarity, ignoring words shorter than 3 chars."""
    words_a = {w for w in a.lower().split() if len(w) >= 3}
    words_b = {w for w in b.lower().split() if len(w) >= 3}
    if not words_a or not words_b:
        return 0.0
    return len(words_a & words_b) / len(words_a | words_b)


def _check_repetition(text: str) -> list[str]:
    sentences = [s.strip() for s in _SENTENCE_SPLIT_RE.split(text) if len(s.strip()) > 20]
    warnings: list[str] = []
    for i in range(len(sentences)):
        for j in range(i + 1, len(sentences)):
            sim = _jaccard(sentences[i], sentences[j])
            if sim >= _JACCARD_THRESHOLD:
                preview = sentences[i][:60]
                warnings.append(
                    f"Tekrarlayan içerik tespit edildi (benzerlik={sim:.2f}): '{preview}…'"
                )
                break   # one warning per sentence pair is enough
    return warnings


# ── Main validator ─────────────────────────────────────────────────────────────

def validate_reasoning(text: str, symbol: str = "") -> ValidationResult:
    """
    Run all quality checks on a Claude reasoning output.

    Returns a ValidationResult. Caller decides whether to reject or warn.
    This function only detects — it does not mutate the text.
    """
    tag = f"[VALIDATOR]{' ' + symbol if symbol else ''}"
    char_count = len(text)
    warnings: list[str] = []

    # ── Length check ───────────────────────────────────────────────────────
    if char_count < _MIN_CHARS:
        reason = f"Çıktı çok kısa: {char_count} karakter (minimum {_MIN_CHARS})"
        logger.warning(f"{tag}: REDDEDİLDİ — {reason}")
        return ValidationResult(
            passed=False,
            rejected=True,
            rejection_reason=reason,
            warnings=[],
            char_count=char_count,
        )

    if char_count > _MAX_CHARS:
        warnings.append(f"Çıktı çok uzun: {char_count} karakter (maksimum {_MAX_CHARS})")

    # ── Rejection pattern scan ─────────────────────────────────────────────
    for pattern, reason in _REJECTION_RULES:
        match = pattern.search(text)
        if match:
            logger.warning(
                f"{tag}: REDDEDİLDİ — {reason} "
                f"(eşleşme: '{match.group()}')"
            )
            return ValidationResult(
                passed=False,
                rejected=True,
                rejection_reason=reason,
                warnings=[],
                char_count=char_count,
            )

    # ── Warning pattern scan ───────────────────────────────────────────────
    for pattern, label in _WARNING_RULES:
        match = pattern.search(text)
        if match:
            warnings.append(f"{label} (eşleşme: '{match.group()}')")

    # ── Required section check ─────────────────────────────────────────────
    for section in _REQUIRED_SECTIONS:
        if section not in text:
            warnings.append(f"Beklenen bölüm bulunamadı: '{section}'")

    # ── Repetition check ──────────────────────────────────────────────────
    warnings.extend(_check_repetition(text))

    return ValidationResult(
        passed=True,   # warnings are non-blocking; only rejection sets passed=False
        rejected=False,
        rejection_reason=None,
        warnings=warnings,
        char_count=char_count,
    )
