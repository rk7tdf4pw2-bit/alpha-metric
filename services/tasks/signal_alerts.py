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

_last_scores: dict[str, int] = {}


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

        logger.info(f"[SCAN] {symbol} checked for signal score")

        score, signals = signal_score.compute(rsi, funding)
        old_score = _last_scores.get(symbol, 0)
        _last_scores[symbol] = score

        if score >= SCORE_THRESHOLD and old_score < SCORE_THRESHOLD:
            slabel = signal_score.label(score)
            logger.info(f"[SIGNAL] {symbol} signal triggered score={score} ({', '.join(signals)})")
            text = signal_alert(symbol, slabel, signals)
            markup = share_markup(app.bot.username)
            for user_id in user_ids:
                if can_send(user_id):
                    await app.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
                    mark_sent(user_id)
                    track("signal_score_alert_sent", symbol=symbol, score=score, user_id=user_id)
                    logger.info(f"[SIGNAL] Signal sent to user {user_id}")
            logger.info(f"Signal alarm: {symbol} skor={score} ({', '.join(signals)})")
