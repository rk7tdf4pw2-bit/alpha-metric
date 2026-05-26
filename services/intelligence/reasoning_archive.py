"""
Reasoning archive — append-only JSONL storage for completed AI analyses.

Why reasoning archives matter:
  A reasoning system without history cannot be evaluated or trusted.
  Archives enable:

  1. Explainability audit  — replay any analysis: what data went in, what came out
  2. Confidence calibration — over time, compare "Yüksek" confidence calls vs outcomes
  3. Regression detection  — if validator warnings increase after a prompt change, catch it
  4. Trust building        — every output is traceable; nothing is a black box
  5. Future improvement    — training data for evaluating reasoning quality patterns

Storage format: JSONL (JSON Lines)
  - One JSON object per line
  - Append-only — never mutated after write
  - Human-readable: inspect with `cat`, `jq`, `grep`
  - Machine-readable: load with pandas, Python's json module, or any JSONL tool

File rotation: size-based
  - When archive exceeds MAX_SIZE_MB, current file is renamed with a timestamp
  - A fresh file starts immediately — no data is lost
  - Rotated files are kept alongside the active file

Archive location: logs/reasoning_archive.jsonl
  Note: On Railway, the filesystem resets on each deploy unless a persistent
  volume is mounted. For production reasoning history, mount a volume at /app/logs.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

from config.settings import LOGS_DIR
from utils.logger import logger


# ── Configuration ──────────────────────────────────────────────────────────────

ARCHIVE_DIR = LOGS_DIR
ARCHIVE_FILE = ARCHIVE_DIR / "reasoning_archive.jsonl"
MAX_SIZE_BYTES = 10 * 1024 * 1024   # 10 MB — ~6 000 records per file


# ── Internal helpers ───────────────────────────────────────────────────────────

def _ensure_dir() -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _rotate_if_needed() -> None:
    """Rename the current archive file if it has grown past MAX_SIZE_BYTES."""
    if not ARCHIVE_FILE.exists():
        return
    size = ARCHIVE_FILE.stat().st_size
    if size < MAX_SIZE_BYTES:
        return
    ts = datetime.now(tz=timezone.utc).strftime("%Y%m%d-%H%M%S")
    rotated = ARCHIVE_DIR / f"reasoning_archive.{ts}.jsonl"
    ARCHIVE_FILE.rename(rotated)
    logger.info(
        f"[ARCHIVE] Dosya döndürüldü: {rotated.name} "
        f"({size / 1024 / 1024:.1f}MB)"
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def write_reasoning_record(record: dict) -> None:
    """
    Append one reasoning record to the JSONL archive.

    Non-blocking: any I/O or serialization error is caught and logged,
    never propagated to the caller. The reasoning pipeline must not fail
    because of an archive write.
    """
    try:
        _ensure_dir()
        _rotate_if_needed()

        line = json.dumps(record, ensure_ascii=False, default=str)
        with ARCHIVE_FILE.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

        logger.info(
            f"[ARCHIVE] {record.get('symbol', '?')}: "
            f"kayıt eklendi "
            f"balance={record.get('balance', '?')} "
            f"confidence={record.get('confidence', '?')} "
            f"chars={len(line)}"
        )

    except Exception as e:
        logger.error(
            f"[ARCHIVE] Yazma hatası — {type(e).__name__}: {e} "
            f"(symbol={record.get('symbol', '?')})"
        )


def build_record(
    symbol: str,
    schema: dict,
    reasoning_text: str,
    confidence: str,
    model_used: str,
    prompt_tokens: int,
    completion_tokens: int,
    reasoning_ms: int,
    validator_warnings: list[str],
    validator_char_count: int,
    fallback_used: bool,
) -> dict:
    """
    Assemble a reasoning archive record.

    Field index:
      archived_at         — when this record was written (ISO 8601, UTC)
      symbol              — trading pair (e.g. BTCUSDT)
      balance             — overall signal balance (aligned/mixed/conflicted/weak)
      confidence          — AI-assigned confidence label (Düşük/Orta/Yüksek)
      fallback_used       — True = no AI reasoning; deterministic fallback shown
      model_used          — Claude model ID or "fallback"
      prompt_tokens       — input tokens consumed
      completion_tokens   — output tokens generated
      total_tokens        — sum, for cost tracking
      reasoning_ms        — end-to-end Claude API duration
      validator_warnings  — quality flags detected (empty = clean pass)
      validator_char_count — length of reasoning text in characters
      reasoning_text      — full Claude output (or fallback summary)
      schema              — complete AnalysisSchema snapshot at time of analysis
    """
    return {
        "archived_at": datetime.now(tz=timezone.utc).isoformat(),
        "symbol": symbol,
        "balance": schema.get("overall_context_balance", "unknown"),
        "confidence": confidence,
        "fallback_used": fallback_used,
        "model_used": model_used,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
        "reasoning_ms": reasoning_ms,
        "validator_warnings": validator_warnings,
        "validator_char_count": validator_char_count,
        "reasoning_text": reasoning_text,
        "schema": schema,
    }
