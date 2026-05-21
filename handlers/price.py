from telegram import Update
from telegram.ext import ContextTypes
from services.market_data import get_price

async def price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /price BTC")
        return

    symbol = context.args[0]
    result = await get_price(symbol)

    if result is None:
        await update.message.reply_text(
            f"'{symbol.upper()}' bulunamadı"
        )
        return

    await update.message.reply_text(
        f"{symbol.upper()}: {result}"
    )
