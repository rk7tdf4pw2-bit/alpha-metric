from telegram import Update
from telegram.ext import ContextTypes
from services.rsi import get_rsi


async def rsi(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /rsi BTC")
        return

    symbol = context.args[0]
    value = await get_rsi(symbol)

    if value is None:
        await update.message.reply_text(f"'{symbol.upper()}' için RSI alınamadı.")
        return

    if value < 30:
        comment = "Aşırı satış bölgesine yaklaşıyor olabilir."
    elif value > 70:
        comment = "Aşırı alım bölgesine yaklaşıyor olabilir."
    else:
        comment = "Normal bölgede."

    await update.message.reply_text(
        f"⚠️ Alpha Metric\n\n"
        f"{symbol.upper()} RSI: {value}\n\n"
        f"{comment}"
    )
