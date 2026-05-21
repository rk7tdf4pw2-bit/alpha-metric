from telegram import InlineKeyboardButton, InlineKeyboardMarkup


def share_markup(bot_username: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton(
            text="Alpha Metric'i Paylaş",
            url=f"https://t.me/{bot_username}",
        )
    ]])
