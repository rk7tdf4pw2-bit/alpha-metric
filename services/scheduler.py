import asyncio
from services.tasks import price_alerts, rsi_alerts, daily_pulse, funding_alerts, signal_alerts
from utils.logger import logger

INTERVAL = 60
HEARTBEAT_CYCLES = 5  # log a heartbeat every 5 scan cycles (~5 minutes)


async def check_watchlists(app):
    cycle = 0
    while True:
        cycle += 1
        # [SCAN] indicates the scheduler started a new full scan cycle.
        logger.info("[SCAN] Running watchlist scan")

        if cycle % HEARTBEAT_CYCLES == 0:
            # [HEARTBEAT] indicates ongoing scheduler liveness in production logs.
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

        await asyncio.sleep(INTERVAL)
