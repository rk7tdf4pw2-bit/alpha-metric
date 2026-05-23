import asyncio
from services.tasks import price_alerts, rsi_alerts, daily_pulse, funding_alerts, signal_alerts
from services.tasks import outcome_tracking, reflection_task
from utils.logger import logger

INTERVAL          = 60
HEARTBEAT_CYCLES  = 5    # log heartbeat every 5 cycles (~5 minutes)
OUTCOME_CYCLES    = 10   # run outcome tracker every 10 cycles (~10 minutes)
REFLECTION_CYCLES = 60   # check reflection every 60 cycles (~1 hour); engine enforces 24h min


async def check_watchlists(app):
    logger.info("[MONITOR] Scheduler loop started — continuous signal monitoring active")
    cycle = 0
    while True:
        cycle += 1
        logger.info(f"[SCAN] Iteration {cycle} started")

        if cycle % HEARTBEAT_CYCLES == 0:
            logger.info("[HEARTBEAT] Scheduler alive")

        for task_name, task in (
            ("price_alerts", price_alerts),
            ("rsi_alerts", rsi_alerts),
            ("daily_pulse", daily_pulse),
            ("funding_alerts", funding_alerts),
            ("signal_alerts", signal_alerts),
        ):
            try:
                await task.run(app)
            except Exception as exc:
                logger.exception(f"[ERROR] {task_name} failed: {exc}")

        # Outcome tracking runs less frequently — Binance API calls per record
        if cycle % OUTCOME_CYCLES == 0:
            try:
                await outcome_tracking.run()
            except Exception as exc:
                logger.exception(f"[ERROR] outcome_tracking failed: {exc}")

        # Reflection engine: hourly check; internally enforces 24h minimum between runs
        if cycle % REFLECTION_CYCLES == 0:
            try:
                await reflection_task.run()
            except Exception as exc:
                logger.exception(f"[ERROR] reflection_task failed: {exc}")

        logger.info(f"[SCAN] Iteration {cycle} completed")
        await asyncio.sleep(INTERVAL)
