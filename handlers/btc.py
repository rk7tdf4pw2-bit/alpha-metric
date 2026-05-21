from telegram import Update
from telegram.ext import ContextTypes
from services.market_data import get_btc_price


async def btc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = await get_btc_price()
        await update.message.reply_text(f"Bitcoin (BTC): {price}")
    except Exception:
        await update.message.reply_text("Fiyat alınamadı. Lütfen tekrar dene.")
