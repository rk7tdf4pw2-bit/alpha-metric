from telegram import Update
from telegram.ext import ContextTypes

from config.settings import STARTER_WATCHLIST
from database.db import add_coins, has_watchlist


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or ""

    if not await has_watchlist(user_id):
        added_count = await add_coins(user_id, username, STARTER_WATCHLIST)
        if added_count > 0:
            watchlist_text = "\n".join(f"• {symbol}" for symbol in STARTER_WATCHLIST)
            await update.message.reply_text(
                "🚀 Alpha Metric'e hoş geldin.\n\n"
                "Başlangıç takip listesi otomatik eklendi:\n\n"
                f"{watchlist_text}\n\n"
                "Bot artık bu coinleri analiz ederek uygun koşullar oluştuğunda sana sinyal gönderecek.\n\n"
                "—\n\n"
                "🚀 Welcome to Alpha Metric.\n\n"
                "Starter watchlist added:\n\n"
                f"{watchlist_text}\n\n"
                "The bot will now analyze these coins and send signals when matching conditions are detected."
            )
            return

    await update.message.reply_text("Merhaba, ben hazırım!")
