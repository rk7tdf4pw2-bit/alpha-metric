import asyncio
from telegram.ext import ApplicationBuilder, CommandHandler

from config.settings import TOKEN
from database.db import init_db
from handlers.start import start
from handlers.price import price
from handlers.watchlist import addcoin, mycoins
from handlers.alert import alert
from handlers.rsi import rsi
from handlers.admin import premium_on, premium_off
from services.scheduler import check_watchlists
from utils.logger import logger


async def on_startup(app):
    await init_db()
    app.create_task(check_watchlists(app))


def main():
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

    logger.info("Bot çalışıyor...")
    app.run_polling()


if __name__ == "__main__":
    main()
