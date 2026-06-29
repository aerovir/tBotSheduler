from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.ext import ExtBot

from tbot_sheduler.bot.notification_service import check_pending_notifications

logger = logging.getLogger(__name__)


async def check_pending(db_session: AsyncSession, bot: Bot | ExtBot) -> int:
    """Check for pending notifications and send them.

    Called at startup and on each update as a heartbeat safety net.
    Delegates to check_pending_notifications() which actually sends.

    Returns:
        Number of notifications sent.
    """
    return await check_pending_notifications(db_session, bot)
