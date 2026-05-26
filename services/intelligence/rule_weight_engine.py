"""
Rule Weight Engine — adaptive contradiction rule weighting from historical outcomes.

For each rule in contradiction_engine, measures: did analyses where this rule fired
produce aligned outcomes more often or less often than the 50% baseline?

weight > 1.0 → rule historically reliable         → boosts balance score
weight < 1.0 → rule historically unreliable       → suppresses balance score
weight = 1.0 → insufficient data or neutral       → no adjustment (safe default)

When all weights are 1.0 (cold start / no data), behavior is identical to the
unweighted contradiction_engine — fully backward compatible.

Storage : logs/weight_archive.jsonl  (append-only snapshots, one per reflection cycle)
Cache   : 1-hour TTL, same pattern as calibration_engine
Horizon : 1h (primary calibration horizon, consistent with reflection_engine)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from config.settings import LOGS_DIR
from utils.logger import logger


# ── Configuration ──────────────────────────────────────────────────────────────

_WEIGHT_FILE    = LOGS_DIR / "weight_archive.jsonl"
_OUTCOME_FILE   = LOGS_DIR / "outcome_archive.jsonl"
_REASONING_FILE = LOGS_DIR / "reasoning_archive.jsonl"

MIN_RULE_SAMPLES = 8     # outcomes where rule fired — below this, weight stays 1.0
ALPHA            = 0.5   # Laplace smoothing — shrinks small samples toward baseline
BASELINE_RATE    = 0.5   # expected alignment rate at random (50/50)
MIN_WEIGHT       = 0.25  # never suppress a rule below 25% of neutral
MAX_WEIGHT       = 2.0   # never boost a rule above 200% of neutral
PRIMARY_HORIZON  = "1h"  # consistent with reflection_engine calibration horizon

_CACHE_TTL = 3600.0
_cache: dict | None = None
_cache_ts: float = 0.0


# ── Rule keys ──────────────────────────────────────────────────────────────────
# Each key uniquely identifies one if/else branch in contradiction_engine.py.
# Prefixed "s_" for supporting rules, "c_" for contradiction rules.
# Weakening rules are single-signal and direction-neutral — not weighted.

SUPPORTING_RULE_KEYS: tuple[str, ...] = (
    "s_stt_bull__htf_bull",
    "s_stt_bear__htf_bear",
    "s_rsi_oversold__mom_decel",
    "s_rsi_overbought__mom_accel",
    "s_rsi_strength__stt_bull",
    "s_rsi_weak__stt_bear",
    "s_vol_high__mom_strong",
    "s_vola_expand__mom_strong",
)

CONTRADICTION_RULE_KEYS: tuple[str, ...] = (
    "c_rsi_oversold__htf_bear",
    "c_rsi_overbought__mom_decel",
    "c_stt_bull__htf_bear",
    "c_stt_bear__htf_bull",
    "c_vol_high__mom_flat",
    "c_vol_low__mom_strong",
    "c_rsi_strength__stt_bear",
    "c_rsi_weak__stt_bull",
    "c_vola_expand__mom_flat",
    "c_rsi_oversold__stt_bull",
)

ALL_RULE_KEYS: tuple[str, ...] = SUPPORTING_RULE_KEYS + CONTRADICTION_RULE_KEYS


# ── Rule condition mirror ──────────────────────────────────────────────────────
# These boolean functions mirror the if/else conditions in contradiction_engine.py
# exactly. They are used to re-evaluate which rules fired for historical records.
# Must be kept in sync with contradiction_engine whenever rules are added/changed.

def rule_fired(ctx: dict, rule_key: str) -> bool:
    """Return True if the given rule would fire for the provided context dict."""
    stt  = ctx.get("short_term_trend", "")
    htf  = ctx.get("higher_tf_trend", "")
    rsi  = ctx.get("rsi_state", "")
    vol  = ctx.get("volume_condition", "")
    vola = ctx.get("volatility_regime", "")
    mom  = ctx.get("momentum", "")

    # ── Supporting rules ───────────────────────────────────────────────────────
    if rule_key == "s_stt_bull__htf_bull":
        return stt == "bullish" and htf == "bullish"
    if rule_key == "s_stt_bear__htf_bear":
        return stt == "bearish" and htf == "bearish"
    if rule_key == "s_rsi_oversold__mom_decel":
        return rsi == "oversold" and mom == "decelerating"
    if rule_key == "s_rsi_overbought__mom_accel":
        return rsi == "overbought" and mom == "accelerating"
    if rule_key == "s_rsi_strength__stt_bull":
        return rsi in ("strengthening", "overbought") and stt == "bullish"
    if rule_key == "s_rsi_weak__stt_bear":
        return rsi in ("weakening", "oversold") and stt == "bearish"
    if rule_key == "s_vol_high__mom_strong":
        return vol == "high" and mom in ("accelerating", "decelerating")
    if rule_key == "s_vola_expand__mom_strong":
        return vola == "expanding" and mom in ("accelerating", "decelerating")

    # ── Contradiction rules ────────────────────────────────────────────────────
    if rule_key == "c_rsi_oversold__htf_bear":
        return rsi == "oversold" and htf == "bearish"
    if rule_key == "c_rsi_overbought__mom_decel":
        return rsi == "overbought" and mom == "decelerating"
    if rule_key == "c_stt_bull__htf_bear":
        return stt == "bullish" and htf == "bearish"
    if rule_key == "c_stt_bear__htf_bull":
        return stt == "bearish" and htf == "bullish"
    if rule_key == "c_vol_high__mom_flat":
        return vol == "high" and mom == "flat"
    if rule_key == "c_vol_low__mom_strong":
        return vol == "low" and mom in ("accelerating", "decelerating")
    if rule_key == "c_rsi_strength__stt_bear":
        return rsi == "strengthening" and stt == "bearish"
    if rule_key == "c_rsi_weak__stt_bull":
        return rsi == "weakening" and stt == "bullish"
    if rule_key == "c_vola_expand__mom_flat":
        return vola == "expanding" and mom == "flat"
    if rule_key == "c_rsi_oversold__stt_bull":
        return rsi == "oversold" and stt == "bullish"

    return False


# ── Output schema ──────────────────────────────────────────────────────────────

class RuleStats(TypedDict):
    count:   int    # outcomes where this rule fired (aligned is not None)
    aligned: int    # count of aligned=True
    rate:    float  # raw alignment rate (aligned/count); 0.0 if count < MIN_RULE_SAMPLES
    weight:  float  # smoothed weight; 1.0 if count < MIN_RULE_SAMPLES


class WeightSnapshot(TypedDict):
    generated_at:        str
    horizon:             str
    total_outcomes:      int            # evaluable outcomes used for computation
    rules_with_data:     int            # rules with count >= MIN_RULE_SAMPLES
    rules:               dict[str, RuleStats]


# ── Archive I/O ────────────────────────────────────────────────────────────────

def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    records.append(json.loads(raw))
    except Exception as exc:
        logger.error(f"[WEIGHTS] Dosya okunamadı {path.name}: {exc}")
    return records


# ── Weight math ────────────────────────────────────────────────────────────────

def _compute_weight(aligned_count: int, total: int) -> float:
    """
    Bayesian-smoothed weight relative to 50% baseline.

    smoothed_rate = (aligned + α) / (total + 2α)
    weight        = clamp(smoothed_rate / baseline, MIN_WEIGHT, MAX_WEIGHT)

    Examples (α=0.5, baseline=0.5):
      aligned=7, total=10  → rate≈0.68 → weight≈1.35
      aligned=5, total=10  → rate≈0.50 → weight≈1.00
      aligned=3, total=10  → rate≈0.32 → weight≈0.65
    """
    smoothed = (aligned_count + ALPHA) / (total + 2 * ALPHA)
    raw = smoothed / BASELINE_RATE
    return round(max(MIN_WEIGHT, min(MAX_WEIGHT, raw)), 4)


# ── Core computation ───────────────────────────────────────────────────────────

def compute_weights() -> WeightSnapshot | None:
    """
    Join outcome_archive with reasoning_archive, re-evaluate which rules fired
    for each historical analysis, compute per-rule Bayesian alignment weights.

    Returns None if total evaluable outcomes < MIN_RULE_SAMPLES.
    """
    outcomes  = _load_jsonl(_OUTCOME_FILE)
    reasoning = _load_jsonl(_REASONING_FILE)

    # Build lookup: (symbol, archived_at) → schema.context
    ctx_lookup: dict[tuple[str, str], dict] = {}
    for rec in reasoning:
        key = (rec.get("symbol", ""), rec.get("archived_at", ""))
        ctx = rec.get("schema", {}).get("context", {})
        if ctx:
            ctx_lookup[key] = ctx

    # Only evaluable outcomes at primary horizon
    evaluable = [
        o for o in outcomes
        if o.get("horizon") == PRIMARY_HORIZON
        and o.get("aligned") is not None
    ]

    if len(evaluable) < MIN_RULE_SAMPLES:
        logger.info(
            f"[WEIGHTS] Yetersiz veri: {len(evaluable)} değerlendirilebilir sonuç "
            f"(minimum {MIN_RULE_SAMPLES})"
        )
        return None

    # Accumulate per-rule counts
    rule_total:   dict[str, int] = {k: 0 for k in ALL_RULE_KEYS}
    rule_aligned: dict[str, int] = {k: 0 for k in ALL_RULE_KEYS}

    for outcome in evaluable:
        join_key = (outcome.get("symbol", ""), outcome.get("analysis_archived_at", ""))
        ctx = ctx_lookup.get(join_key)
        if ctx is None:
            continue
        is_aligned: bool = outcome["aligned"]
        for rule_key in ALL_RULE_KEYS:
            if rule_fired(ctx, rule_key):
                rule_total[rule_key]   += 1
                rule_aligned[rule_key] += int(is_aligned)

    # Build per-rule stats
    rules: dict[str, RuleStats] = {}
    rules_with_data = 0
    for key in ALL_RULE_KEYS:
        total   = rule_total[key]
        aligned = rule_aligned[key]
        if total >= MIN_RULE_SAMPLES:
            rules_with_data += 1
            rate   = round(aligned / total, 4)
            weight = _compute_weight(aligned, total)
        else:
            rate   = 0.0
            weight = 1.0  # neutral — insufficient data; do not adjust
        rules[key] = RuleStats(count=total, aligned=aligned, rate=rate, weight=weight)

    snapshot = WeightSnapshot(
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        horizon=PRIMARY_HORIZON,
        total_outcomes=len(evaluable),
        rules_with_data=rules_with_data,
        rules=rules,
    )

    logger.info(
        f"[WEIGHTS] Hesaplandı: "
        f"outcomes={len(evaluable)} "
        f"rules_with_data={rules_with_data}/{len(ALL_RULE_KEYS)}"
    )
    return snapshot


def archive_weights(snapshot: WeightSnapshot) -> None:
    """Append weight snapshot to weight_archive.jsonl and update cache."""
    global _cache, _cache_ts
    try:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(snapshot, ensure_ascii=False, default=str)
        with _WEIGHT_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        _cache    = dict(snapshot)
        _cache_ts = time.time()
        logger.info(
            f"[WEIGHTS] Arşivlendi: "
            f"rules_with_data={snapshot['rules_with_data']} "
            f"total_outcomes={snapshot['total_outcomes']}"
        )
    except Exception as exc:
        logger.error(f"[WEIGHTS] Arşiv yazma hatası: {exc}")


def load_active_weights() -> dict[str, float]:
    """
    Return {rule_key: weight} from the latest snapshot (1h TTL cache).
    Falls back to all-neutral weights if no data — safe default preserves
    existing contradiction_engine behavior exactly.
    """
    global _cache, _cache_ts
    now = time.time()

    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return {k: v["weight"] for k, v in _cache["rules"].items()}

    records = _load_jsonl(_WEIGHT_FILE)
    if not records:
        return {k: 1.0 for k in ALL_RULE_KEYS}

    try:
        latest    = records[-1]
        _cache    = latest
        _cache_ts = now
        weights   = {k: v["weight"] for k, v in latest["rules"].items()}
        non_neutral = sum(1 for w in weights.values() if w != 1.0)
        logger.info(
            f"[WEIGHTS] Yüklendi: "
            f"non_neutral={non_neutral}/{len(ALL_RULE_KEYS)} "
            f"generated_at={latest.get('generated_at', '?')}"
        )
        return weights
    except Exception as exc:
        logger.warning(f"[WEIGHTS] Yüklenemedi — nötr ağırlıklar kullanılıyor: {exc}")
        return {k: 1.0 for k in ALL_RULE_KEYS}
