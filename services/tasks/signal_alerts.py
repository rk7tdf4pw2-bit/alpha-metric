import time

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
# Aynı sembol için iki alarm arasındaki minimum süre (saniye).
# Rising-edge dedektörü yerine kullanılıyor; restart bağımlılığını ortadan kaldırır.
SYMBOL_COOLDOWN_SECONDS = 4 * 60 * 60  # 4 saat

_last_alert_time: dict[str, float] = {}


async def run(app):
    entries = await get_all_watchlists()
    if not entries:
        return

    premium = set(await get_premium_users())

    symbol_users: dict[str, list[int]] = {}
    for user_id, symbol in entries:
        if user_id in premium:
            symbol_users.setdefault(symbol, []).append(user_id)

    for symbol, user_ids in symbol_users.items():
        rsi = await get_rsi(symbol)
        funding = await get_funding_rate(symbol) or 0.0
        if rsi is None:
            continue

        score, signals = signal_score.compute(rsi, funding)
        logger.info(f"[SIGNAL] {symbol} score={score} rsi={rsi:.1f} funding={funding:.4f}")

        if score < SCORE_THRESHOLD:
            continue

        now = time.time()
        seconds_since_last = now - _last_alert_time.get(symbol, 0)
        if seconds_since_last < SYMBOL_COOLDOWN_SECONDS:
            logger.info(
                f"[SIGNAL] {symbol} on cooldown — {int((SYMBOL_COOLDOWN_SECONDS - seconds_since_last) / 60)}m remaining"
            )
            continue

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
