from database.db import get_all_watchlists
from services.rsi import get_rsi
from services.cooldown import can_send, mark_sent
from services.analytics import track
from templates.messages import rsi_alert
from utils.logger import logger

# (user_id, symbol) → son RSI durumu: 'normal' | 'oversold' | 'overbought'
_rsi_states: dict[tuple, str] = {}


async def run(app):
    entries = await get_all_watchlists()
    if not entries:
        return

    symbol_users: dict[str, list[int]] = {}
    for user_id, symbol in entries:
        symbol_users.setdefault(symbol, []).append(user_id)

    for symbol, user_ids in symbol_users.items():
        value = await get_rsi(symbol)
        if value is None:
            continue

        if value < 30:
            new_state = "oversold"
        elif value > 70:
            new_state = "overbought"
        else:
            new_state = "normal"

        for user_id in user_ids:
            key = (user_id, symbol)
            old_state = _rsi_states.get(key, "normal")
            _rsi_states[key] = new_state

            if new_state != "normal" and new_state != old_state:
                if can_send(user_id):
                    await app.bot.send_message(chat_id=user_id, text=rsi_alert(symbol, value, new_state))
                    mark_sent(user_id)
                    track("rsi_alert_sent", symbol=symbol, state=new_state, rsi=value, user_id=user_id)
                    logger.info(f"RSI alarmı: {symbol} {new_state} (RSI: {value}) → kullanıcı {user_id}")
                else:
                    logger.info(f"RSI cooldown: {symbol} → kullanıcı {user_id} atlandı")
