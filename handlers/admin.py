from telegram import Update
from telegram.ext import ContextTypes
from database.db import set_premium, is_premium_user


async def premium_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if await is_premium_user(user_id):
        await update.message.reply_text("Zaten premium kullanıcısınız.")
        return
    await set_premium(user_id, True)
    await update.message.reply_text("Premium aktif edildi.")


async def premium_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not await is_premium_user(user_id):
        await update.message.reply_text("Zaten ücretsiz kullanıcısınız.")
        return
    await set_premium(user_id, False)
    await update.message.reply_text("Premium devre dışı bırakıldı.")
