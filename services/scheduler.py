import asyncio
import traceback

from telegram.ext import CallbackContext

from services.tasks import price_alerts, rsi_alerts, daily_pulse, funding_alerts, signal_alerts
from services.tasks import outcome_tracking, reflection_task
from utils.logger import logger

INTERVAL          = 60
HEARTBEAT_CYCLES  = 5    # log heartbeat every 5 cycles (~5 minutes)
OUTCOME_CYCLES    = 10   # run outcome tracker every 10 cycles (~10 minutes)
REFLECTION_CYCLES = 60   # check reflection every 60 cycles (~1 hour); engine enforces 24h min

_CYCLE_COUNTER = 0
_TASKS = (
    ("price_alerts",   price_alerts),
    ("rsi_alerts",     rsi_alerts),
    ("daily_pulse",    daily_pulse),
    ("funding_alerts", funding_alerts),
    ("signal_alerts",  signal_alerts),
)


async def check_watchlists(app):
    global _CYCLE_COUNTER
    _CYCLE_COUNTER += 1
    cycle = _CYCLE_COUNTER

    logger.info("[MONITOR] Monitoring cycle started")
    logger.info(f"[SCAN] Iteration {cycle} started")

    if cycle % HEARTBEAT_CYCLES == 0:
        logger.info(f"[HEARTBEAT] Scheduler alive — cycle={cycle}")

    for task_name, task in _TASKS:
        try:
            result = await task.run(app)
            if task_name == "signal_alerts" and result is not None:
                symbols_checked, signals_found = result
                logger.info(
                    f"[MONITOR] Signal summary — symbols_checked={symbols_checked} signals_found={signals_found}"
                )
        except asyncio.CancelledError:
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

    logger.info(f"[MONITOR] Monitoring cycle completed — iteration={cycle}")


async def _monitor_job(context: CallbackContext) -> None:
    try:
        await check_watchlists(context.application)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.error(
            f"[MONITOR] Scheduler job failed:\n{traceback.format_exc()}"
        )


async def schedule_monitoring(app):
    logger.info("[MONITOR] Scheduling continuous signal monitoring")
    app.signal_monitor_job = app.job_queue.run_repeating(
        callback=_monitor_job,
        interval=INTERVAL,
        first=INTERVAL,
        name="signal_monitor",
    )
    logger.info("[MONITOR] Initial signal scan starting immediately")
    await check_watchlists(app)
    logger.info("[MONITOR] Signal monitor scheduled and running")
