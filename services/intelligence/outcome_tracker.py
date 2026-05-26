"""
Outcome tracker — evaluates what actually happened after an analysis was generated.

Why outcome tracking matters:
  A reasoning system without outcome history cannot be calibrated.
  Without knowing whether "Yüksek güven + bullish" was correct 60% or 40% of the time,
  the confidence label carries no real meaning.

  This module answers: "Did the interpretation hold?"

  That question enables:
    1. Confidence calibration — high-confidence aligned calls should outperform random
    2. Reasoning quality improvement — which signal combinations produce reliable readings?
    3. Auditable trust — every analysis has a traceable outcome; nothing is hidden
    4. Pattern detection — spot systematic biases (e.g., oversensitive RSI signals)

  This is NOT:
    - A trading system
    - A PnL calculator
    - A backtester
  It is a reasoning evaluation log.

Evaluation horizons:
  15m — short-term signal consistency
  1h  — trend confirmation window
  4h  — higher-timeframe alignment check

Storage: logs/outcome_archive.jsonl (append-only JSONL)

Data source: Binance klines (historical, always available for past timestamps)
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import TypedDict

from config.settings import LOGS_DIR
from utils.http import get as http_get
from utils.logger import logger


# ── Configuration ──────────────────────────────────────────────────────────────

_ARCHIVE_DIR    = LOGS_DIR
_REASONING_FILE = _ARCHIVE_DIR / "reasoning_archive.jsonl"
_OUTCOME_FILE   = _ARCHIVE_DIR / "outcome_archive.jsonl"

BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines"

# How many seconds after the analysis before each horizon is evaluated
HORIZONS: dict[str, int] = {
    "15m": 15 * 60,
    "1h":  60 * 60,
    "4h":  4 * 60 * 60,
}

# Extra buffer before attempting evaluation — ensures the horizon candle is fully closed
_EVAL_BUFFER_SECONDS = 120

# Kline params per horizon: (interval, limit)
# limit = (horizon / interval_seconds) + 1 entry candle
_HORIZON_KLINES: dict[str, tuple[str, int]] = {
    "15m": ("1m",  16),   # 16 × 1m = 15m + 1 entry
    "1h":  ("5m",  13),   # 13 × 5m ≈ 65m (1h + 1)
    "4h":  ("15m", 17),   # 17 × 15m = 255m (4h + 1)
}

# Minimum price change (%) to classify as "up" or "down" vs "sideways"
_DIRECTION_THRESHOLD_PCT = 0.4

# How far back to scan the reasoning archive (covers 4h horizon + safety margin)
_SCAN_WINDOW_HOURS = 6.0


# ── Output schema ──────────────────────────────────────────────────────────────

class OutcomeRecord(TypedDict):
    evaluated_at: str           # ISO 8601 — when this outcome was written
    analysis_archived_at: str   # ISO 8601 — when the source analysis was generated
    symbol: str
    horizon: str                # "15m" / "1h" / "4h"
    analysis_balance: str       # aligned / mixed / conflicted / weak
    analysis_confidence: str    # Düşük / Orta / Yüksek
    interpretation: str         # bullish / bearish / inconclusive
    entry_price: float          # price at start of evaluation window
    exit_price: float           # price at end of evaluation window
    change_pct: float           # (exit - entry) / entry × 100
    direction: str              # up / down / sideways
    period_high: float          # highest price during window
    period_low: float           # lowest price during window
    volatility_range_pct: float # (high - low) / entry × 100
    aligned: bool | None        # True/False if interpretable, None if inconclusive


# ── In-memory deduplication ────────────────────────────────────────────────────
# Key format: "BTCUSDT:2026-05-23T10:30:00+00:00:1h"
# Loaded from outcome_archive.jsonl on first run, then updated in-memory.

_evaluated: set[str] = set()
_loaded: bool = False


def _eval_key(symbol: str, archived_at: str, horizon: str) -> str:
    return f"{symbol}:{archived_at}:{horizon}"


def _load_existing_outcomes() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    if not _OUTCOME_FILE.exists():
        return
    try:
        count = 0
        with _OUTCOME_FILE.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                rec = json.loads(raw)
                _evaluated.add(_eval_key(
                    rec.get("symbol", ""),
                    rec.get("analysis_archived_at", ""),
                    rec.get("horizon", ""),
                ))
                count += 1
        logger.info(f"[OUTCOME] Başlangıç: {count} mevcut değerlendirme yüklendi")
    except Exception as e:
        logger.warning(f"[OUTCOME] Mevcut kayıtlar yüklenemedi: {e}")


# ── Archive I/O ────────────────────────────────────────────────────────────────

def _read_reasoning_records() -> list[dict]:
    """Read reasoning records from the last _SCAN_WINDOW_HOURS hours."""
    if not _REASONING_FILE.exists():
        return []
    cutoff_ts = time.time() - _SCAN_WINDOW_HOURS * 3600
    records: list[dict] = []
    try:
        with _REASONING_FILE.open("r", encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                rec = json.loads(raw)
                archived_at = rec.get("archived_at", "")
                if not archived_at:
                    continue
                try:
                    ts = datetime.fromisoformat(archived_at).timestamp()
                except ValueError:
                    continue
                if ts >= cutoff_ts:
                    records.append(rec)
    except Exception as e:
        logger.error(f"[OUTCOME] Arşiv okunamadı: {type(e).__name__}: {e}")
    return records


def _write_outcome(record: OutcomeRecord) -> None:
    try:
        _ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record, ensure_ascii=False, default=str)
        with _OUTCOME_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        logger.info(
            f"[OUTCOME] {record['symbol']} {record['horizon']}: "
            f"change={record['change_pct']:+.2f}% "
            f"direction={record['direction']} "
            f"aligned={record['aligned']} "
            f"volatility={record['volatility_range_pct']:.2f}%"
        )
    except Exception as e:
        logger.error(
            f"[OUTCOME] Yazma hatası — {type(e).__name__}: {e} "
            f"(symbol={record.get('symbol', '?')} horizon={record.get('horizon', '?')})"
        )


# ── Binance price fetcher ──────────────────────────────────────────────────────

async def _fetch_klines_for_window(
    symbol: str,
    start_ts: float,
    interval: str,
    limit: int,
) -> list | None:
    """
    Fetch `limit` klines starting at `start_ts` (unix seconds).
    Returns raw Binance kline list, or None on failure.
    """
    data = await http_get(BINANCE_KLINE_URL, params={
        "symbol": symbol,
        "interval": interval,
        "startTime": int(start_ts * 1000),
        "limit": limit,
    })
    if not isinstance(data, list):
        logger.warning(
            f"[OUTCOME] {symbol}: kline yanıtı geçersiz "
            f"interval={interval} limit={limit} start={start_ts:.0f}"
        )
        return None
    if len(data) < limit:
        logger.warning(
            f"[OUTCOME] {symbol}: kline eksik "
            f"beklenen={limit} gelen={len(data)} "
            f"interval={interval} start={start_ts:.0f} → ertelendi"
        )
        return None
    return data


# ── Direction and alignment ────────────────────────────────────────────────────

def _classify_direction(change_pct: float) -> str:
    if change_pct > _DIRECTION_THRESHOLD_PCT:
        return "up"
    if change_pct < -_DIRECTION_THRESHOLD_PCT:
        return "down"
    return "sideways"


def _interpretation_direction(balance: str, short_term_trend: str) -> str:
    """
    Derive the directional claim from the analysis.
    Only "aligned" balance with a clear trend produces a directional reading.
    Mixed/conflicted/weak analyses are inconclusive — cannot be wrong or right.
    """
    if balance == "aligned":
        if short_term_trend == "bullish":
            return "bullish"
        if short_term_trend == "bearish":
            return "bearish"
    return "inconclusive"


def _compute_alignment(interpretation: str, direction: str) -> bool | None:
    """
    True  = market moved with interpretation
    False = market moved against interpretation
    None  = not applicable (inconclusive interpretation or sideways market)
    """
    if interpretation == "inconclusive" or direction == "sideways":
        return None
    return (interpretation == "bullish") == (direction == "up")


# ── Single-horizon evaluator ───────────────────────────────────────────────────

async def _evaluate_one(
    rec: dict,
    horizon: str,
    archived_at_ts: float,
    now: float,
) -> OutcomeRecord | None:
    """
    Try to evaluate one (reasoning record, horizon) pair.
    Returns an OutcomeRecord if evaluation succeeds, None otherwise.
    """
    due_at = archived_at_ts + HORIZONS[horizon] + _EVAL_BUFFER_SECONDS
    if now < due_at:
        return None  # horizon not yet passed

    symbol = rec.get("symbol", "")
    key = _eval_key(symbol, rec["archived_at"], horizon)
    if key in _evaluated:
        return None  # already evaluated

    # Skip fallback records — no AI interpretation to validate
    if rec.get("fallback_used", True):
        _evaluated.add(key)  # mark so we don't check again
        return None

    interval, limit = _HORIZON_KLINES[horizon]
    klines = await _fetch_klines_for_window(symbol, archived_at_ts, interval, limit)
    if klines is None:
        return None  # try again next cycle (not marked as evaluated)

    opens  = [float(k[1]) for k in klines]
    highs  = [float(k[2]) for k in klines]
    lows   = [float(k[3]) for k in klines]
    closes = [float(k[4]) for k in klines]

    entry_price = opens[0]
    if entry_price == 0:
        _evaluated.add(key)
        return None

    exit_price       = closes[-1]
    period_high      = max(highs)
    period_low       = min(lows)
    change_pct       = (exit_price - entry_price) / entry_price * 100
    volatility_pct   = (period_high - period_low) / entry_price * 100
    direction        = _classify_direction(change_pct)

    schema           = rec.get("schema", {})
    balance          = schema.get("overall_context_balance", "unknown")
    trend            = schema.get("context", {}).get("short_term_trend", "neutral")
    interpretation   = _interpretation_direction(balance, trend)
    aligned          = _compute_alignment(interpretation, direction)

    _evaluated.add(key)
    return OutcomeRecord(
        evaluated_at=datetime.now(tz=timezone.utc).isoformat(),
        analysis_archived_at=rec["archived_at"],
        symbol=symbol,
        horizon=horizon,
        analysis_balance=balance,
        analysis_confidence=rec.get("confidence", "?"),
        interpretation=interpretation,
        entry_price=round(entry_price, 6),
        exit_price=round(exit_price, 6),
        change_pct=round(change_pct, 3),
        direction=direction,
        period_high=round(period_high, 6),
        period_low=round(period_low, 6),
        volatility_range_pct=round(volatility_pct, 3),
        aligned=aligned,
    )


# ── Public entry point ─────────────────────────────────────────────────────────

async def evaluate_pending() -> None:
    """
    Find and evaluate all reasoning records that are past their horizon windows.
    Called periodically by the scheduler — not on every cycle.
    """
    _load_existing_outcomes()

    records = _read_reasoning_records()
    if not records:
        logger.info("[OUTCOME] Tarama: değerlendirilecek yeni analiz bulunamadı")
        return

    now = time.time()
    written = 0
    pending = 0

    for rec in records:
        try:
            archived_ts = datetime.fromisoformat(rec["archived_at"]).timestamp()
        except (ValueError, KeyError):
            continue

        for horizon in HORIZONS:
            outcome = await _evaluate_one(rec, horizon, archived_ts, now)
            if outcome is not None:
                _write_outcome(outcome)
                written += 1
            else:
                pending += 1

    logger.info(
        f"[OUTCOME] Tarama tamamlandı: "
        f"yeni_kayıt={written} beklemede={pending} "
        f"toplam_değerlendirilen={len(_evaluated)}"
    )
