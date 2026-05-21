from telegram import Update
from telegram.ext import ContextTypes
from database.db import add_coin, get_coins


async def addcoin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Kullanım: /addcoin BTC")
        return

    user = update.effective_user
    symbol = context.args[0].upper()
    added = await add_coin(user.id, user.username or "", symbol)

    if added:
        await update.message.reply_text(f"{symbol} takip listenize eklendi.")
    else:
        await update.message.reply_text(f"{symbol} zaten listenizde var.")


async def mycoins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    coins = await get_coins(user.id)

    if not coins:
        await update.message.reply_text("Takip listesi boş. /addcoin BTC ile ekleyebilirsiniz.")
        return

    coin_list = "\n".join(f"• {c}" for c in coins)
    await update.message.reply_text(f"Takip ettiğiniz coinler:\n{coin_list}")
