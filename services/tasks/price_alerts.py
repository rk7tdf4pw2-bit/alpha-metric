from database.db import get_pending_alerts, mark_alert_triggered
from services.market_data import get_price
from services.cooldown import can_send, mark_sent
from services.analytics import track
from templates.messages import price_alert
from utils.logger import logger


async def run(app):
    alerts = await get_pending_alerts()
    for alert_id, user_id, symbol, condition, target in alerts:
        price_str = await get_price(symbol)
        if price_str is None:
            continue

        logger.info(f"[SCAN] {symbol} checked for price alert")

        current = float(price_str.replace("$", "").replace(",", ""))
        triggered = (condition == "above" and current >= target) or \
                    (condition == "below" and current <= target)

        if triggered:
            await mark_alert_triggered(alert_id)
            logger.info(f"[SIGNAL] {symbol} price alert triggered target={target}")
            if can_send(user_id):
                await app.bot.send_message(chat_id=user_id, text=price_alert(symbol, price_str))
                mark_sent(user_id)
                track("alert_sent", symbol=symbol, condition=condition, target=target, user_id=user_id)
                logger.info(f"[SIGNAL] Signal sent to user {user_id}")
            else:
                logger.info(f"Alarm cooldown: {symbol} → kullanıcı {user_id} atlandı")
