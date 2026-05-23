import asyncio
import traceback

from services.tasks import price_alerts, rsi_alerts, daily_pulse, funding_alerts, signal_alerts
from services.tasks import outcome_tracking, reflection_task
from utils.logger import logger

INTERVAL          = 60
HEARTBEAT_CYCLES  = 5    # log heartbeat every 5 cycles (~5 minutes)
OUTCOME_CYCLES    = 10   # run outcome tracker every 10 cycles (~10 minutes)
REFLECTION_CYCLES = 60   # check reflection every 60 cycles (~1 hour); engine enforces 24h min

_TASKS = (
    ("price_alerts",   price_alerts),
    ("rsi_alerts",     rsi_alerts),
    ("daily_pulse",    daily_pulse),
    ("funding_alerts", funding_alerts),
    ("signal_alerts",  signal_alerts),
)


async def check_watchlists(app):
    logger.info("[MONITOR] Scheduler loop started — continuous signal monitoring active")
    cycle = 0
    while True:
        cycle += 1
        logger.info(f"[SCAN] Iteration {cycle} started")

        if cycle % HEARTBEAT_CYCLES == 0:
            logger.info(f"[HEARTBEAT] Scheduler alive — cycle={cycle}")

        for task_name, task in _TASKS:
            try:
                await task.run(app)
            except asyncio.CancelledError:
                # Re-raise immediately — do NOT log as an error.
                # CancelledError means PTB is shutting down; let it propagate cleanly.
                raise
            except Exception:
                logger.error(
                    f"[ERROR] {task_name} failed:\n{traceback.format_exc()}"
                )

        if cycle % OUTCOME_CYCLES == 0:
            try:
                await outcome_tracking.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    f"[ERROR] outcome_tracking failed:\n{traceback.format_exc()}"
                )

        if cycle % REFLECTION_CYCLES == 0:
            try:
                await reflection_task.run()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error(
                    f"[ERROR] reflection_task failed:\n{traceback.format_exc()}"
                )

        logger.info(f"[SCAN] Iteration {cycle} completed — sleeping {INTERVAL}s")
        await asyncio.sleep(INTERVAL)
