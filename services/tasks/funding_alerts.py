from database.db import get_premium_users
from services.funding import get_funding_rate
from services.cooldown import can_send, mark_sent
from services.analytics import track
from templates.messages import funding_alert
from templates.keyboards import share_markup
from utils.logger import logger

THRESHOLD_HIGH =  0.0005   # +0.05% → long kalabalık
THRESHOLD_LOW  = -0.0005   # -0.05% → short kalabalık

_last_state: str = "normal"


async def run(app):
    global _last_state

    rate = await get_funding_rate("BTC")
    if rate is None:
        return

    if rate > THRESHOLD_HIGH:
        new_state = "long_crowded"
    elif rate < THRESHOLD_LOW:
        new_state = "short_crowded"
    else:
        new_state = "normal"

    if new_state != "normal" and new_state != _last_state:
        users = await get_premium_users()
        text = funding_alert(rate, new_state)
        markup = share_markup(app.bot.username)
        for user_id in users:
            if can_send(user_id):
                await app.bot.send_message(chat_id=user_id, text=text, reply_markup=markup)
                mark_sent(user_id)
                track("funding_alert_sent", state=new_state, rate=f"{rate:.6f}", user_id=user_id)
        logger.info(f"Funding alarmı: {new_state} (rate: {rate:.6f})")

    _last_state = new_state
