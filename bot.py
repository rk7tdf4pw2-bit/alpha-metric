import asyncio
import sys
from telegram.ext import ApplicationBuilder, CommandHandler

from config.settings import TOKEN
from database.db import init_db
from handlers.start import start
from handlers.price import price
from handlers.watchlist import addcoin, mycoins
from handlers.alert import alert
from handlers.rsi import rsi
from handlers.admin import premium_on, premium_off
from handlers.analyze import analyze
from services.scheduler import check_watchlists
from utils.logger import logger


async def _watch_scheduler(app):
    """Crash-restart wrapper for the main scheduler.

    Keeps signal monitoring alive indefinitely. Logs crashes to Railway.
    Re-raises CancelledError so PTB can shut down cleanly.
    """
    while True:
        try:
            await check_watchlists(app)
        except asyncio.CancelledError:
            logger.info("[MONITOR] Scheduler cancelled — shutting down cleanly")
            raise
        except Exception as exc:
            logger.exception(f"[MONITOR] Scheduler crashed: {exc}. Restarting in 30 seconds...")
            await asyncio.sleep(30)


async def on_startup(app):
    """Initialize database and start background tasks on bot startup."""
    await init_db()
    app.create_task(_watch_scheduler(app))
    logger.info("✓ Bot initialization complete - database ready, signal monitor started")


def main():
    """Main entry point for the Telegram bot."""
    # Validate TOKEN before starting
    if not TOKEN or TOKEN.strip() == "":
        logger.error("❌ TELEGRAM_TOKEN not set! Set TELEGRAM_TOKEN environment variable and retry.")
        sys.exit(1)

    asyncio.set_event_loop(asyncio.new_event_loop())

    app = ApplicationBuilder().token(TOKEN).post_init(on_startup).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("price", price))
    app.add_handler(CommandHandler("addcoin", addcoin))
    app.add_handler(CommandHandler("mycoins", mycoins))
    app.add_handler(CommandHandler("alert", alert))
    app.add_handler(CommandHandler("rsi", rsi))
    app.add_handler(CommandHandler("premium_on", premium_on))
    app.add_handler(CommandHandler("premium_off", premium_off))
    app.add_handler(CommandHandler("analyze", analyze))
    logger.info("[BOT] analyze handler registered")

    logger.info("🤖 Alpha Metric Bot starting... (polling mode)")
    try:
        app.run_polling()
    except KeyboardInterrupt:
        logger.info("⏹ Bot stopped by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"❌ Critical error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
