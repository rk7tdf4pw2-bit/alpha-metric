"""
Calibration Engine — disciplined reasoning calibration guidance for Alpha Metric.

This engine reads reflection insights from the historical reflection archive
and generates explicit, traceable calibration directives.

It is NOT an adaptive or self-modifying agent.
It does NOT rewrite prompts, change code, or retrain models.
It only produces human-readable guidance for reasoning behavior:
  - confidence caps
  - caution flags
  - instability markers
  - historical warnings

Every calibration decision is grounded in a named reflection insight,
so the output remains auditable and deterministic.
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from services.intelligence.reflection_engine import ReflectionReport
from utils.logger import logger


# ── Archive configuration ──────────────────────────────────────────────────────

_ARCHIVE_DIR = Path("logs")
_CALIBRATION_FILE = _ARCHIVE_DIR / "calibration_archive.jsonl"
_REFLECTION_FILE = _ARCHIVE_DIR / "reflection_archive.jsonl"

# ── Module-level cache (1 saatlik TTL) ────────────────────────────────────────

_cache: dict | None = None
_cache_ts: float = 0.0
_CACHE_TTL = 3600.0

# ── Sabitler ───────────────────────────────────────────────────────────────────

_INJECT_ANCHOR = "Yukarıdaki yapılandırılmış bağlamı analiz et"
_CONFIDENCE_ORDER: dict[str, int] = {"Düşük": 0, "Orta": 1, "Yüksek": 2}


# ── Output schemas ─────────────────────────────────────────────────────────────

class CalibrationHint(TypedDict):
    type: str                # confidence_cap / caution_flag / instability_marker / historical_warning
    severity: str            # info / caution / concern
    condition: str           # when this calibration should apply
    recommendation: str      # what to do in practice
    detail: str              # traceable detail from the reflection insight
    source_insight: str      # insight type that generated this calibration


class CalibrationReport(TypedDict):
    generated_at: str
    reflection_source: str
    reflection_generated_at: str
    reflection_period_start: str
    reflection_period_end: str
    reflection_insights: list[str]
    calibrations: list[CalibrationHint]
    skipped_calibrations: list[CalibrationHint]


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
    except Exception as exc:
        logger.error(f"[CALIBRATE] Dosya okunamadı {path.name}: {type(exc).__name__}: {exc}")
    return records



def _load_latest_reflection() -> ReflectionReport | None:
    records = _load_jsonl(_REFLECTION_FILE)
    if not records:
        logger.info("[CALIBRATE] Refleksiyon arşivi boş — kalibrasyon atlandı")
        return None

    latest = records[-1]
    generated_at = latest.get("generated_at", "unknown")
    logger.info(
        f"[CALIBRATE] En son refleksiyon raporu yüklendi generated_at={generated_at} "
        f"insights={len(latest.get('insights', []))}"
    )
    return latest  # type: ignore[return-value]


# ── Calibration decision engine ─────────────────────────────────────────────────


def _build_hint(
    insight: dict,
    hint_type: str,
    condition: str,
    recommendation: str,
) -> CalibrationHint:
    return CalibrationHint(
        type=hint_type,
        severity=insight.get("severity", "info"),
        condition=condition,
        recommendation=recommendation,
        detail=insight.get("detail", insight.get("finding", "")),
        source_insight=insight.get("type", "unknown"),
    )



def _directive_for_insight(insight: dict) -> CalibrationHint | None:
    insight_type = insight.get("type", "unknown")
    severity = insight.get("severity", "info")
    finding = insight.get("finding", "")

    if insight_type == "false_confidence":
        return _build_hint(
            insight,
            hint_type="confidence_cap",
            condition=(
                "Yüksek confidence atanmış analizlerde 1h horizon için daha düşük hizalanma gözlendi"
            ),
            recommendation=(
                "1h horizon için Yüksek güven seviyesini Orta'ya düşürmeyi değerlendirin; "
                "güveni daha muhafazakar ifade edin"
            ),
        )

    if insight_type == "overconfidence":
        return _build_hint(
            insight,
            hint_type="confidence_cap",
            condition=(
                "Yüksek confidence, Orta confidence'dan daha kötü performans gösterdi"
            ),
            recommendation=(
                "Yüksek güven atamasını azaltın; potansiyel olarak Yüksek yerine Orta kullanın"
            ),
        )

    if insight_type == "conflicted_high_confidence":
        return _build_hint(
            insight,
            hint_type="caution_flag",
            condition=(
                "Analiz çelişkili (conflicted) olduğu halde yüksek confidence atandı"
            ),
            recommendation=(
                "Çelişkili bağlamlarda yönsel ifadeleri yumuşatın ve "
                "güvenli, ölçülü bir dil kullanın"
            ),
        )

    if insight_type == "balance_inversion":
        return _build_hint(
            insight,
            hint_type="instability_marker",
            condition=(
                "'Aligned' sinyal dengesinin beklenenden düşük güvenilirlik gösterdiği tarihsel durum"
            ),
            recommendation=(
                "'Aligned' analizleri daha volatil kabul edin; belirsizliği ve riskleri daha öne çıkarın"
            ),
        )

    if insight_type == "validator_correlation":
        return _build_hint(
            insight,
            hint_type="historical_warning",
            condition=(
                "Validator uyarısı taşıyan analizler daha düşük hizalanma oranına sahip"
            ),
            recommendation=(
                "Validator uyarısı olan durumlarda güven seviyesini düşürmeyi veya "
                "daha temkinli ifade etmeyi değerlendirin"
            ),
        )

    if insight_type == "confidence_ordering":
        # Info-level confirmation: no calibration needed, but traceable.
        return None

    if insight_type == "balance_reliability":
        if severity != "info":
            return _build_hint(
                insight,
                hint_type="historical_warning",
                condition=(
                    "Sinyal balance kalibrasyonu belirli horizon'larda zayıf olabilir"
                ),
                recommendation=(
                    "Bu horizonlarda daha temkinli dil kullanın ve güven seviyesini yeniden kontrol edin"
                ),
            )
        return None

    # Unknown insight types are skipped but traceable.
    return None



def generate_calibration(
    report: ReflectionReport | None = None,
) -> CalibrationReport | None:
    if report is None:
        report = _load_latest_reflection()
    if report is None:
        return None

    insights = report.get("insights", [])
    calibrations: list[CalibrationHint] = []
    skipped_calibrations: list[CalibrationHint] = []

    for insight in insights:
        directive = _directive_for_insight(insight)
        if directive is None:
            skipped = _build_hint(
                insight,
                hint_type="historical_warning",
                condition="Bu insight için otomatik kalibrasyon gerekmedi.",
                recommendation="Mevcut kalibrasyon durumu kararlı görünüyor.",
            )
            skipped_calibrations.append(skipped)
            logger.info(
                f"[CALIBRATE] Skipped calibration for insight={insight.get('type')} "
                f"severity={insight.get('severity')}"
            )
            continue

        calibrations.append(directive)
        logger.info(
            f"[CALIBRATE] Applied calibration={directive['type']} "
            f"source={directive['source_insight']} "
            f"severity={directive['severity']}"
        )

    report_generated_at = report.get("generated_at", "unknown")
    calibration_report: CalibrationReport = CalibrationReport(
        generated_at=datetime.now(tz=timezone.utc).isoformat(),
        reflection_source=str(_REFLECTION_FILE),
        reflection_generated_at=report_generated_at,
        reflection_period_start=report.get("period_start", ""),
        reflection_period_end=report.get("period_end", ""),
        reflection_insights=[insight.get("type", "unknown") for insight in insights],
        calibrations=calibrations,
        skipped_calibrations=skipped_calibrations,
    )

    logger.info(
        f"[CALIBRATE] Calibration report generated: "
        f"calibrations={len(calibrations)} skipped={len(skipped_calibrations)}"
    )
    return calibration_report


def archive_calibration(report: CalibrationReport) -> None:
    global _cache, _cache_ts
    try:
        _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(report, ensure_ascii=False, default=str)
        with _CALIBRATION_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.info(
            f"[CALIBRATE] Arşivlendi: calibrations={len(report['calibrations'])} "
            f"skipped={len(report['skipped_calibrations'])}"
        )
        # Önbelleği güncelle
        _cache = dict(report)
        _cache_ts = time.time()
    except Exception as exc:
        logger.error(
            f"[CALIBRATE] Arşiv yazma hatası: {type(exc).__name__}: {exc}"
        )


# ── Aktif kalibrasyon yükleme (önbellekli) ────────────────────────────────────

def load_active_calibration() -> CalibrationReport | None:
    """En son kalibrasyon raporunu yükler (1 saatlik TTL önbellek)."""
    global _cache, _cache_ts
    now = time.time()
    if _cache is not None and (now - _cache_ts) < _CACHE_TTL:
        return _cache  # type: ignore[return-value]

    records = _load_jsonl(_CALIBRATION_FILE)
    if not records:
        return None

    try:
        latest = records[-1]
        _cache = latest
        _cache_ts = now
        logger.info(
            f"[CALIBRATE] Yüklendi: calibrations={len(latest.get('calibrations', []))} "
            f"generated_at={latest.get('generated_at', '?')}"
        )
        return latest  # type: ignore[return-value]
    except Exception as exc:
        logger.warning(f"[CALIBRATE] Yüklenemedi: {type(exc).__name__}: {exc}")
        return None


# ── Aktif ipucu filtreleme ─────────────────────────────────────────────────────

def get_active_hints(
    schema: dict,
    calibration: CalibrationReport | None,
) -> list[CalibrationHint]:
    """Mevcut analize uygun kalibrasyon ipuçlarını döndürür (concern + caution)."""
    if calibration is None:
        return []

    hints = [
        h for h in calibration.get("calibrations", [])
        if h.get("severity") in ("concern", "caution")
    ]
    return hints


# ── Prompt enjeksiyonu ─────────────────────────────────────────────────────────

def format_calibration_hints(hints: list[CalibrationHint]) -> str:
    """Aktif ipuçlarından Claude için okunabilir bir uyarı bloğu oluşturur."""
    if not hints:
        return ""
    lines = ["### Tarihsel Kalibrasyon Notları (Geçmiş Performanstan)"]
    for h in hints:
        icon = "⚠️" if h["severity"] == "concern" else "ℹ️"
        lines.append(f"{icon} {h['recommendation']}")
    return "\n".join(lines)


def inject_into_prompt(prompt: str, hints: list[CalibrationHint]) -> str:
    """Kalibrasyon ipuçlarını prompt'a enjekte eder (anchor noktasının önüne)."""
    hint_block = format_calibration_hints(hints)
    if not hint_block or _INJECT_ANCHOR not in prompt:
        return prompt
    return prompt.replace(_INJECT_ANCHOR, f"{hint_block}\n\n{_INJECT_ANCHOR}", 1)


# ── Güven tavanı ───────────────────────────────────────────────────────────────

def apply_confidence_cap(
    confidence: str,
    hints: list[CalibrationHint],
) -> tuple[str, str | None]:
    """
    (nihai_güven, uygulanan_ipucu_etiketi | None) döndürür.
    Yalnızca concern seviyesindeki confidence_cap ipuçları tavan uygular.
    """
    cap_hints = [
        h for h in hints
        if h.get("type") == "confidence_cap" and h.get("severity") == "concern"
    ]
    if not cap_hints:
        return confidence, None

    current = _CONFIDENCE_ORDER.get(confidence, 99)
    # Concern-level cap → Orta
    cap_target = "Orta"
    cap_level = _CONFIDENCE_ORDER.get(cap_target, 99)

    if current > cap_level:
        label = cap_hints[0].get("source_insight", "kalibrasyon")
        logger.info(
            f"[CALIBRATE] Güven tavanı uygulandı: {confidence} → {cap_target} "
            f"(kaynak: {label})"
        )
        return cap_target, label

    return confidence, None
