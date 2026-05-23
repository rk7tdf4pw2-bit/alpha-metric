import asyncio
import time
import traceback

from database.db import get_all_watchlists, get_premium_users
from services.rsi import get_rsi
from services.funding import get_funding_rate
from services import signal_score
from services.cooldown import can_send, mark_sent
from services.analytics import track
from templates.messages import signal_alert
from templates.keyboards import share_markup
from utils.logger import logger

SCORE_THRESHOLD = 2
# Time-based per-symbol cooldown replaces the old rising-edge detector.
# The rising-edge approach required a restart to re-trigger; this fires every 4h if score stays high.
SYMBOL_COOLDOWN_SECONDS = 4 * 60 * 60  # 4 hours

_last_alert_time: dict[str, float] = {}


async def _scan_symbol(app, symbol: str, user_ids: list[int]) -> int:
    """Scan one symbol and send alerts. Returns number of alerts sent."""
    rsi = await get_rsi(symbol)
    funding = await get_funding_rate(symbol) or 0.0
    if rsi is None:
        return 0

    score, signals = signal_score.compute(rsi, funding)
    logger.info(f"[SIGNAL] {symbol} score={score} rsi={rsi:.1f} funding={funding:.4f}")

    if score < SCORE_THRESHOLD:
        return 0

    now = time.time()
    seconds_since_last = now - _last_alert_time.get(symbol, 0)
    if seconds_since_last < SYMBOL_COOLDOWN_SECONDS:
        logger.info(
            f"[SIGNAL] {symbol} on cooldown — "
            f"{int((SYMBOL_COOLDOWN_SECONDS - seconds_since_last) / 60)}m remaining"
        )
        return 0

    slabel = signal_score.label(score)
    logger.info(f"[SIGNAL] {symbol} alert triggered score={score} ({', '.join(signals)})")
    _last_alert_time[symbol] = now

    text = signal_alert(symbol, slabel, signals)
    markup = share_markup(app.bot.username)
    alerts_sent = 0
    for user_id in user_ids:
        if can_send(user_id):
            await app.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
            mark_sent(user_id)
            track("signal_score_alert_sent", symbol=symbol, score=score, user_id=user_id)
            alerts_sent += 1

    logger.info(f"[SIGNAL] {symbol} alerts_sent={alerts_sent} score={score} signals={signals}")
    return alerts_sent


async def run(app):
    entries = await get_all_watchlists()
    if not entries:
        return 0, 0

    premium = set(await get_premium_users())

    symbol_users: dict[str, list[int]] = {}
    for user_id, symbol in entries:
        if user_id in premium:
            symbol_users.setdefault(symbol, []).append(user_id)

    if not symbol_users:
        return 0, 0

    symbols_scanned = 0
    total_alerts = 0

    for symbol, user_ids in symbol_users.items():
        try:
            sent = await _scan_symbol(app, symbol, user_ids)
            symbols_scanned += 1
            total_alerts += sent
        except asyncio.CancelledError:
            raise  # propagate cleanly — do not swallow shutdown signal
        except Exception:
            logger.error(f"[SIGNAL] {symbol} scan crashed:\n{traceback.format_exc()}")

    logger.info(
        f"[SIGNAL] Scan complete — symbols_scanned={symbols_scanned} "
        f"total_alerts={total_alerts} premium_users={len(premium)}"
    )
    return symbols_scanned, total_alerts
