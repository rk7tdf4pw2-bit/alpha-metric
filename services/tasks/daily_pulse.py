from datetime import date
from database.db import get_all_users, get_premium_users, get_all_watchlists
from services.market_data import get_price
from services.rsi import get_rsi
from services.cooldown import can_send, mark_sent
from services.analytics import track
from templates.messages import daily_pulse as pulse_message
from utils.logger import logger

_last_pulse_date: date | None = None


async def run(app):
    global _last_pulse_date
    today = date.today()
    if _last_pulse_date == today:
        return

    price = await get_price("BTC")
    rsi = await get_rsi("BTC")
    if price is None or rsi is None:
        return

    users = await get_all_users()
    if not users:
        return

    text = pulse_message(price, rsi)
    sent = 0
    for user_id in users:
        if can_send(user_id):
            await app.bot.send_message(chat_id=user_id, text=text)
            mark_sent(user_id)
            sent += 1

    premium = await get_premium_users()
    watchlists = await get_all_watchlists()

    _last_pulse_date = today
    logger.info(f"Günlük pulse gönderildi → {sent}/{len(users)} kullanıcı")
    track("premium_user_count", count=len(premium))
    track("watchlist_count", count=len(watchlists))
