from services.intelligence.outcome_tracker import evaluate_pending
from utils.logger import logger


async def run() -> None:
    """Scheduled task: evaluate reasoning outcomes for past analyses."""
    try:
        await evaluate_pending()
    except Exception as e:
        logger.error(f"[OUTCOME] Görev beklenmeyen hata: {type(e).__name__}: {e}")
