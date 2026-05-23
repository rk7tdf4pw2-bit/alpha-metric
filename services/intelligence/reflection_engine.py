"""
Reflection Engine — deterministic self-evaluation and reasoning calibration layer.

Philosophy:
  Explainability requires accountability.
  A reasoning system that cannot evaluate its own track record
  is not trustworthy — it simply repeats patterns without learning.

  This engine reads past reasoning outcomes and generates calibration insights.
  Every insight is computed from observed data, expressed as a human-readable
  finding, and archived for audit.

  It does NOT:
    - Rewrite any rules or system prompts
    - Modify model behavior or parameters
    - Make predictions about future performance
    - Operate without human oversight

  It ONLY:
    - Reads historical archives (reasoning + outcomes)
    - Computes alignment statistics per group
    - Surfaces patterns that deviate from expected calibration
    - Generates named, auditable insights with sample sizes

  Design for avoiding black-box self-learning:
    Every insight is named, quantified, and explainable.
    Example: "conflicted balance + Yüksek confidence: 3/8 = 37.5% aligned at 1h"
    A human can verify this by reading the outcome_archive.jsonl directly.
    There is no latent representation, no gradient update, no hidden state.
    The system learns by surfacing facts, not by absorbing them silently.

Insight severity scale:
  info    — neutral observation; no action required
  caution — mild calibration gap; worth monitoring
  concern — clear calibration failure; confidence should be adjusted downward

Storage: logs/reflection_archive.jsonl (append-only JSONL)
"""

import json
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from utils.logger import logger


# ── Configuration ──────────────────────────────────────────────────────────────

_ARCHIVE_DIR      = Path("logs")
_REASONING_FILE   = _ARCHIVE_DIR / "reasoning_archive.jsonl"
_OUTCOME_FILE     = _ARCHIVE_DIR / "outcome_archive.jsonl"
_REFLECTION_FILE  = _ARCHIVE_DIR / "reflection_archive.jsonl"

MIN_SAMPLE_SIZE              = 5    # minimum outcomes to draw a conclusion
MIN_OUTCOMES_FOR_REFLECTION  = 10   # minimum total evaluable outcomes to produce a report
CONCERN_ALIGNMENT_THRESHOLD  = 45.0 # below this % → concern-level severity
CAUTION_ALIGNMENT_THRESHOLD  = 55.0 # below this % → caution-level severity
OVERCONFIDENCE_GAP           = 10.0 # if Yüksek alignment is this much below Orta → overconfidence flag


# ── Data schemas ───────────────────────────────────────────────────────────────

class AlignmentStats(TypedDict):
    total: int      # evaluable outcomes (aligned is not None)
    aligned: int    # aligned = True
    against: int    # aligned = False
    rate_pct: float # aligned / total × 100


class ReflectionInsight(TypedDict):
    type: str          # category of insight
    severity: str      # "info" / "caution" / "concern"
    finding: str       # human-readable conclusion
    detail: str        # numeric breakdown — fully auditable
    sample_size: int
    recommendation: str


class ReflectionReport(TypedDict):
    generated_at: str
    period_start: str          # earliest analysis in the evaluated window
    period_end: str            # latest analysis
    reasoning_records: int     # total reasoning records read
    evaluable_outcomes: int    # outcomes with aligned != None
    by_horizon: dict           # horizon → AlignmentStats
    by_confidence: dict        # confidence → horizon → AlignmentStats
    by_balance: dict           # balance → horizon → AlignmentStats
    false_confidence_count: int
    false_confidence_rate_pct: float
    validator_warning_impact: dict   # "warned" / "clean" → AlignmentStats
    insights: list[ReflectionInsight]


# ── Archive loaders ────────────────────────────────────────────────────────────

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
    except Exception as e:
        logger.error(f"[REFLECT] Dosya okunamadı {path.name}: {e}")
    return records


# ── Core statistics ────────────────────────────────────────────────────────────

def _alignment_stats(outcomes: list[dict]) -> AlignmentStats:
    """Compute alignment statistics for a list of outcome records."""
    evaluable = [o for o in outcomes if o.get("aligned") is not None]
    if not evaluable:
        return AlignmentStats(total=0, aligned=0, against=0, rate_pct=0.0)
    aligned = sum(1 for o in evaluable if o["aligned"] is True)
    against = len(evaluable) - aligned
    return AlignmentStats(
        total=len(evaluable),
        aligned=aligned,
        against=against,
        rate_pct=round(aligned / len(evaluable) * 100, 1),
    )


def _severity(rate_pct: float) -> str:
    if rate_pct < CONCERN_ALIGNMENT_THRESHOLD:
        return "concern"
    if rate_pct < CAUTION_ALIGNMENT_THRESHOLD:
        return "caution"
    return "info"


def _group(outcomes: list[dict], key_fn) -> dict:
    """Group outcomes into a dict by key_fn result."""
    groups: dict = defaultdict(list)
    for o in outcomes:
        groups[key_fn(o)].append(o)
    return dict(groups)


# ── Insight generators ─────────────────────────────────────────────────────────
# Each function is independently testable and produces a specific type of finding.

def _insights_false_confidence(outcomes: list[dict]) -> list[ReflectionInsight]:
    """
    Detect cases where Yüksek confidence was assigned but the outcome was misaligned.
    This is the clearest calibration failure signal.
    """
    insights = []
    for horizon in ("15m", "1h", "4h"):
        h_outcomes = [o for o in outcomes if o.get("horizon") == horizon]
        yuksek = [o for o in h_outcomes
                  if o.get("analysis_confidence") == "Yüksek"
                  and o.get("aligned") is not None]
        if len(yuksek) < MIN_SAMPLE_SIZE:
            continue
        false_conf = [o for o in yuksek if o["aligned"] is False]
        rate = len(false_conf) / len(yuksek) * 100
        sev = "concern" if rate > 40.0 else ("caution" if rate > 25.0 else "info")
        insights.append(ReflectionInsight(
            type="false_confidence",
            severity=sev,
            finding=(
                f"Yüksek güven, {horizon} horizon'da {len(false_conf)}/{len(yuksek)} vakada "
                f"yanlış yön ({rate:.1f}% hata oranı)"
            ),
            detail=(
                f"confidence=Yüksek, horizon={horizon}: "
                f"aligned={len(yuksek) - len(false_conf)} false_conf={len(false_conf)} "
                f"rate={len(yuksek) - len(false_conf)}/{len(yuksek)}={100 - rate:.1f}%"
            ),
            sample_size=len(yuksek),
            recommendation=(
                "Yüksek güven atamasını gözden geçir — bu pattern'de Orta daha uygun olabilir"
                if sev != "info" else "Yüksek güven kalibrasyonu makul görünüyor"
            ),
        ))
    return insights


def _insights_confidence_ordering(
    by_conf_horizon: dict,
    horizons: list[str],
) -> list[ReflectionInsight]:
    """
    Verify that Yüksek confidence outperforms Orta, and Orta outperforms Düşük.
    Violation = overconfidence in labeling.
    """
    insights = []
    for horizon in horizons:
        stats: dict[str, AlignmentStats] = {}
        for conf in ("Yüksek", "Orta", "Düşük"):
            group = by_conf_horizon.get((conf, horizon), [])
            s = _alignment_stats(group)
            if s["total"] >= MIN_SAMPLE_SIZE:
                stats[conf] = s

        if "Yüksek" not in stats or "Orta" not in stats:
            continue

        yuksek_rate = stats["Yüksek"]["rate_pct"]
        orta_rate   = stats["Orta"]["rate_pct"]
        gap = orta_rate - yuksek_rate

        if gap >= OVERCONFIDENCE_GAP:
            insights.append(ReflectionInsight(
                type="overconfidence",
                severity="concern" if gap >= 20.0 else "caution",
                finding=(
                    f"Yüksek güven, {horizon} horizon'da Orta güvenin altında performans gösteriyor "
                    f"({yuksek_rate:.1f}% vs {orta_rate:.1f}%)"
                ),
                detail=(
                    f"horizon={horizon}: "
                    f"Yüksek={yuksek_rate:.1f}% (n={stats['Yüksek']['total']}) "
                    f"Orta={orta_rate:.1f}% (n={stats['Orta']['total']}) "
                    f"fark={gap:.1f}pp"
                ),
                sample_size=stats["Yüksek"]["total"] + stats["Orta"]["total"],
                recommendation=(
                    f"{horizon} horizon'da güven atamasını aşağı çek: "
                    "Yüksek → Orta, Orta → Düşük yönünde yeniden değerlendir"
                ),
            ))
        elif yuksek_rate >= orta_rate:
            insights.append(ReflectionInsight(
                type="confidence_ordering",
                severity="info",
                finding=(
                    f"Güven sıralaması {horizon}'da tutarlı: "
                    f"Yüksek={yuksek_rate:.1f}% ≥ Orta={orta_rate:.1f}%"
                ),
                detail=(
                    f"horizon={horizon}: "
                    f"Yüksek={yuksek_rate:.1f}% (n={stats['Yüksek']['total']}) "
                    f"Orta={orta_rate:.1f}% (n={stats['Orta']['total']})"
                ),
                sample_size=stats["Yüksek"]["total"] + stats["Orta"]["total"],
                recommendation="Güven kalibrasyonu bu horizon için makul — mevcut yaklaşımı koru",
            ))
    return insights


def _insights_balance_reliability(
    by_balance_horizon: dict,
    horizons: list[str],
) -> list[ReflectionInsight]:
    """
    'aligned' balance should yield the highest alignment rate.
    If 'mixed' or 'conflicted' outperforms 'aligned', something is miscalibrated.
    """
    insights = []
    for horizon in horizons:
        stats: dict[str, AlignmentStats] = {}
        for bal in ("aligned", "mixed", "conflicted", "weak"):
            group = by_balance_horizon.get((bal, horizon), [])
            s = _alignment_stats(group)
            if s["total"] >= MIN_SAMPLE_SIZE:
                stats[bal] = s

        if "aligned" not in stats:
            continue

        aligned_rate = stats["aligned"]["rate_pct"]

        # Check if "aligned" balance is actually the most reliable
        better_than_aligned = [
            (bal, s) for bal, s in stats.items()
            if bal != "aligned" and s["rate_pct"] > aligned_rate + 5.0
        ]
        if better_than_aligned:
            worst_bal, worst_stats = max(better_than_aligned, key=lambda x: x[1]["rate_pct"])
            insights.append(ReflectionInsight(
                type="balance_inversion",
                severity="caution",
                finding=(
                    f"{horizon}: '{worst_bal}' sinyal dengesi, 'aligned'den daha yüksek "
                    f"hizalanma oranına sahip ({worst_stats['rate_pct']:.1f}% vs {aligned_rate:.1f}%)"
                ),
                detail=(
                    f"horizon={horizon}: "
                    + " ".join(
                        f"{b}={s['rate_pct']:.1f}%(n={s['total']})"
                        for b, s in stats.items()
                    )
                ),
                sample_size=sum(s["total"] for s in stats.values()),
                recommendation=(
                    "Contradiction engine kurallarını gözden geçir — "
                    "'aligned' sınıflandırması beklenenden az güvenilir"
                ),
            ))
        else:
            sev = _severity(aligned_rate)
            insights.append(ReflectionInsight(
                type="balance_reliability",
                severity=sev,
                finding=(
                    f"Hizalı sinyal dengesi (aligned) {horizon}'da "
                    f"%{aligned_rate:.1f} oranıyla en güvenilir kategori"
                    if aligned_rate == max((s["rate_pct"] for s in stats.values()), default=0)
                    else f"Hizalı sinyal dengesi {horizon}'da %{aligned_rate:.1f} hizalanma oranında"
                ),
                detail=" ".join(
                    f"{b}={s['rate_pct']:.1f}%(n={s['total']})"
                    for b, s in sorted(stats.items(), key=lambda x: -x[1]["rate_pct"])
                ),
                sample_size=sum(s["total"] for s in stats.values()),
                recommendation=(
                    "Mevcut balance sınıflandırması güvenilir — değişiklik gerekmez"
                    if sev == "info" else
                    f"'aligned' balance {horizon}'da {aligned_rate:.1f}% — yeterli veri bekle"
                ),
            ))
    return insights


def _insights_conflicted_high_conf(outcomes: list[dict]) -> list[ReflectionInsight]:
    """
    'conflicted' balance + 'Yüksek' confidence is a known dangerous combination.
    Surface explicitly if it appears in the data.
    """
    insights = []
    for horizon in ("15m", "1h", "4h"):
        group = [
            o for o in outcomes
            if o.get("horizon") == horizon
            and o.get("analysis_balance") == "conflicted"
            and o.get("analysis_confidence") == "Yüksek"
            and o.get("aligned") is not None
        ]
        if len(group) < MIN_SAMPLE_SIZE:
            continue
        stats = _alignment_stats(group)
        sev = _severity(stats["rate_pct"])
        insights.append(ReflectionInsight(
            type="conflicted_high_confidence",
            severity=sev,
            finding=(
                f"Çelişkili bağlam (conflicted) + Yüksek güven: "
                f"{horizon}'da %{stats['rate_pct']:.1f} hizalanma oranı"
            ),
            detail=(
                f"conflicted+Yüksek, horizon={horizon}: "
                f"aligned={stats['aligned']} against={stats['against']} "
                f"rate={stats['rate_pct']:.1f}%"
            ),
            sample_size=stats["total"],
            recommendation=(
                "Çelişkili sinyal dengesinde Yüksek güven atama — "
                "bu kombinasyonda güven seviyesini Orta veya Düşük olarak değerlendir"
                if sev != "info" else
                "Çelişkili bağlamda Yüksek güven bu örnekte makul görünüyor"
            ),
        ))
    return insights


def _insights_validator_impact(
    outcomes: list[dict],
    reasoning_records: list[dict],
) -> list[ReflectionInsight]:
    """
    Determine whether validator warnings correlate with lower alignment rates.
    Join outcomes with reasoning records by (symbol, analysis_archived_at).
    """
    # Build lookup: (symbol, archived_at) → has_warnings
    warning_lookup: dict[tuple, bool] = {}
    for rec in reasoning_records:
        key = (rec.get("symbol", ""), rec.get("archived_at", ""))
        warning_lookup[key] = bool(rec.get("validator_warnings"))

    warned_outcomes = []
    clean_outcomes  = []

    for o in outcomes:
        if o.get("aligned") is None:
            continue
        key = (o.get("symbol", ""), o.get("analysis_archived_at", ""))
        has_warning = warning_lookup.get(key, False)
        if has_warning:
            warned_outcomes.append(o)
        else:
            clean_outcomes.append(o)

    if len(warned_outcomes) < MIN_SAMPLE_SIZE or len(clean_outcomes) < MIN_SAMPLE_SIZE:
        return []

    warned_stats = _alignment_stats(warned_outcomes)
    clean_stats  = _alignment_stats(clean_outcomes)
    gap = clean_stats["rate_pct"] - warned_stats["rate_pct"]

    if gap >= 10.0:
        sev = "concern" if gap >= 20.0 else "caution"
        finding = (
            f"Validator uyarısı olan analizler daha düşük hizalanma oranına sahip "
            f"(%{warned_stats['rate_pct']:.1f} vs temiz %{clean_stats['rate_pct']:.1f}, "
            f"fark={gap:.1f}pp)"
        )
        recommendation = (
            "Validator uyarıları başarısızlıkla ilişkili — "
            "uyarılı analizlerde güven seviyesini düşürmeyi değerlendir"
        )
    else:
        sev = "info"
        finding = (
            f"Validator uyarıları hizalanma oranını belirgin şekilde etkilemiyor "
            f"(uyarılı=%{warned_stats['rate_pct']:.1f} temiz=%{clean_stats['rate_pct']:.1f})"
        )
        recommendation = "Validator mevcut kural seti bu veri setinde belirgin bir sinyal üretmiyor"

    return [ReflectionInsight(
        type="validator_correlation",
        severity=sev,
        finding=finding,
        detail=(
            f"warned: aligned={warned_stats['aligned']} against={warned_stats['against']} "
            f"rate={warned_stats['rate_pct']:.1f}% (n={warned_stats['total']}) | "
            f"clean: aligned={clean_stats['aligned']} against={clean_stats['against']} "
            f"rate={clean_stats['rate_pct']:.1f}% (n={clean_stats['total']})"
        ),
        sample_size=warned_stats["total"] + clean_stats["total"],
        recommendation=recommendation,
    )]


# ── Main report builder ────────────────────────────────────────────────────────

def generate_reflection() -> ReflectionReport | None:
    """
    Read historical archives, compute calibration metrics, and generate a reflection report.
    Returns None if insufficient data is available.
    """
    outcomes  = _load_jsonl(_OUTCOME_FILE)
    reasoning = _load_jsonl(_REASONING_FILE)

    evaluable = [o for o in outcomes if o.get("aligned") is not None]
    if len(evaluable) < MIN_OUTCOMES_FOR_REFLECTION:
        logger.info(
            f"[REFLECT] Yetersiz veri: {len(evaluable)} değerlendirilebilir sonuç "
            f"(minimum {MIN_OUTCOMES_FOR_REFLECTION})"
        )
        return None

    # ── Period metadata ────────────────────────────────────────────────────
    all_timestamps = [
        o.get("analysis_archived_at", "")
        for o in outcomes
        if o.get("analysis_archived_at")
    ]
    period_start = min(all_timestamps) if all_timestamps else ""
    period_end   = max(all_timestamps) if all_timestamps else ""

    # ── Group outcomes ─────────────────────────────────────────────────────
    horizons = ["15m", "1h", "4h"]
    by_horizon = {
        h: _alignment_stats([o for o in evaluable if o.get("horizon") == h])
        for h in horizons
    }

    by_conf_horizon: dict[tuple, list] = defaultdict(list)
    by_balance_horizon: dict[tuple, list] = defaultdict(list)
    for o in evaluable:
        by_conf_horizon[(o.get("analysis_confidence", "?"), o.get("horizon", "?"))].append(o)
        by_balance_horizon[(o.get("analysis_balance", "unknown"), o.get("horizon", "?"))].append(o)

    by_confidence = {
        conf: {
            h: _alignment_stats(by_conf_horizon.get((conf, h), []))
            for h in horizons
        }
        for conf in ("Yüksek", "Orta", "Düşük")
    }
    by_balance = {
        bal: {
            h: _alignment_stats(by_balance_horizon.get((bal, h), []))
            for h in horizons
        }
        for bal in ("aligned", "mixed", "conflicted", "weak")
    }

    # ── False confidence ───────────────────────────────────────────────────
    false_conf_events = [
        o for o in evaluable
        if o.get("analysis_confidence") == "Yüksek"
        and o.get("aligned") is False
        and o.get("horizon") == "1h"   # 1h as primary calibration horizon
    ]
    total_yuksek_1h = [
        o for o in evaluable
        if o.get("analysis_confidence") == "Yüksek"
        and o.get("horizon") == "1h"
    ]
    false_conf_rate = (
        len(false_conf_events) / len(total_yuksek_1h) * 100
        if total_yuksek_1h else 0.0
    )

    # ── Validator impact ───────────────────────────────────────────────────
    warning_lookup: dict[tuple, bool] = {
        (r.get("symbol", ""), r.get("archived_at", "")): bool(r.get("validator_warnings"))
        for r in reasoning
    }
    warned = [
        o for o in evaluable
        if warning_lookup.get((o.get("symbol", ""), o.get("analysis_archived_at", "")))
    ]
    clean = [o for o in evaluable if o not in warned]
    validator_impact = {
        "warned": _alignment_stats(warned),
        "clean":  _alignment_stats(clean),
    }

    # ── Generate insights ──────────────────────────────────────────────────
    insights: list[ReflectionInsight] = []
    insights.extend(_insights_false_confidence(evaluable))
    insights.extend(_insights_confidence_ordering(by_conf_horizon, horizons))
    insights.extend(_insights_balance_reliability(by_balance_horizon, horizons))
    insights.extend(_insights_conflicted_high_conf(evaluable))
    insights.extend(_insights_validator_impact(evaluable, reasoning))

    # Sort: concern > caution > info
    _severity_order = {"concern": 0, "caution": 1, "info": 2}
    insights.sort(key=lambda i: _severity_order.get(i["severity"], 9))

    logger.info(
        f"[REFLECT] Rapor oluşturuldu: "
        f"outcomes={len(evaluable)} insights={len(insights)} "
        f"concerns={sum(1 for i in insights if i['severity'] == 'concern')} "
        f"cautions={sum(1 for i in insights if i['severity'] == 'caution')}"
    )

    return ReflectionReport(
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        period_start=period_start,
        period_end=period_end,
        reasoning_records=len(reasoning),
        evaluable_outcomes=len(evaluable),
        by_horizon=by_horizon,
        by_confidence=by_confidence,
        by_balance=by_balance,
        false_confidence_count=len(false_conf_events),
        false_confidence_rate_pct=round(false_conf_rate, 1),
        validator_warning_impact=validator_impact,
        insights=insights,
    )


# ── Archive writer ─────────────────────────────────────────────────────────────

def archive_reflection(report: ReflectionReport) -> None:
    """Append the reflection report to reflection_archive.jsonl."""
    try:
        _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(report, ensure_ascii=False, default=str)
        with _REFLECTION_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.info(
            f"[REFLECT] Arşivlendi: "
            f"insights={len(report['insights'])} "
            f"period={report['period_start'][:10]}→{report['period_end'][:10]}"
        )
    except Exception as e:
        logger.error(f"[REFLECT] Arşiv yazma hatası: {type(e).__name__}: {e}")
