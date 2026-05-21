from datetime import datetime, timedelta

COOLDOWN_MINUTES = 10

_last_sent: dict[int, datetime] = {}


def can_send(user_id: int) -> bool:
    last = _last_sent.get(user_id)
    if last is None:
        return True
    return datetime.now() - last >= timedelta(minutes=COOLDOWN_MINUTES)


def mark_sent(user_id: int):
    _last_sent[user_id] = datetime.now()
