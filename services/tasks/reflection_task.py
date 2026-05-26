"""
Scheduled reflection task — runs at most once per 24 hours.

Frequency is controlled by a timestamp file (logs/.last_reflection),
so the 24-hour minimum survives bot restarts and Railway redeploys.
"""

import time
from pathlib import Path

from config.settings import LOGS_DIR
from services.intelligence.calibration_engine import archive_calibration, generate_calibration
from services.intelligence.reflection_engine import archive_reflection, generate_reflection
from services.intelligence.rule_weight_engine import archive_weights, compute_weights
from utils.logger import logger

_LAST_RUN_FILE = LOGS_DIR / ".last_reflection"
_MIN_INTERVAL_H  = 24
_MIN_INTERVAL_S  = _MIN_INTERVAL_H * 3600


def _hours_since_last_run() -> float:
    if not _LAST_RUN_FILE.exists():
        return float("inf")
    try:
        last = float(_LAST_RUN_FILE.read_text().strip())
        return (time.time() - last) / 3600
    except Exception:
        return float("inf")


def _mark_ran() -> None:
    try:
        _LAST_RUN_FILE.parent.mkdir(parents=True, exist_ok=True)
        _LAST_RUN_FILE.write_text(str(time.time()))
    except Exception as e:
        logger.warning(f"[REFLECT] Son çalışma zamanı kaydedilemedi: {e}")


async def run() -> None:
    hours_ago = _hours_since_last_run()
    if hours_ago < _MIN_INTERVAL_H:
        return  # ran recently — skip silently

    logger.info(
        f"[REFLECT] Yansıma değerlendirmesi başlatılıyor "
        f"(son çalışma: {hours_ago:.1f}s önce)"
    )
    try:
        report = generate_reflection()
        if report is None:
            logger.info("[REFLECT] Yeterli veri yok — yansıma ertelendi")
        else:
            archive_reflection(report)
            # Yansıma raporundan kalibrasyon bağlamını üret ve arşivle
            try:
                calibration = generate_calibration(report)
                if calibration is not None:
                    archive_calibration(calibration)
            except Exception as cal_e:
                logger.error(f"[REFLECT] Kalibrasyon hatası: {type(cal_e).__name__}: {cal_e}")

            # Kural ağırlıklarını güncelle — contradiction engine'e geçmiş verinin etkisi
            try:
                weight_snapshot = compute_weights()
                if weight_snapshot is not None:
                    archive_weights(weight_snapshot)
            except Exception as w_e:
                logger.error(f"[REFLECT] Kural ağırlığı hesaplama hatası: {type(w_e).__name__}: {w_e}")
        _mark_ran()
    except Exception as e:
        logger.error(f"[REFLECT] Beklenmeyen hata: {type(e).__name__}: {e}")
