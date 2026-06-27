from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def start_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /start command."""
    user = update.effective_user
    logger.info(
        "User %s (%d) started the bot", user.full_name, user.id
    )
    await update.message.reply_text(
        "👋 Привет! Я бот для бронирования расписания.\n\n"
        "Команды:\n"
        "/start — показать это сообщение\n"
        "/health — состояние системы\n\n"
        "Доступные функции будут расширяться."
    )
