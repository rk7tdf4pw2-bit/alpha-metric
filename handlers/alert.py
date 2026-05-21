from telegram import Update
from telegram.ext import ContextTypes
from database.db import add_alert


async def alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 3:
        await update.message.reply_text("Kullanım: /alert BTC above 100000")
        return

    symbol, condition, target_str = context.args
    condition = condition.lower()

    if condition not in ("above", "below"):
        await update.message.reply_text("Koşul 'above' veya 'below' olmalı.")
        return

    try:
        target = float(target_str)
    except ValueError:
        await update.message.reply_text("Fiyat sayı olmalı. Örnek: /alert BTC above 100000")
        return

    await add_alert(update.effective_user.id, symbol, condition, target)
    direction = "üzerine" if condition == "above" else "altına"
    await update.message.reply_text(
        f"{symbol.upper()} ${target:,.0f} {direction} düşünce sizi uyaracağım."
    )
