from utils.logger import logger


def track(event: str, **data):
    parts = " ".join(f"{k}={v}" for k, v in data.items())
    logger.info(f"[event] {event} {parts}".strip())
