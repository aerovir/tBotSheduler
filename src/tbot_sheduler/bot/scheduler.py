from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

logger = logging.getLogger(__name__)


async def check_pending(db_session: AsyncSession) -> int:
    """Check for pending notifications that should have been sent.

    Called at startup and on each update as a heartbeat safety net.

    Returns:
        Number of pending notifications found.
    """
    result = await db_session.execute(
        text(
            "SELECT COUNT(*) FROM notification "
            "WHERE sent = 0 AND notify_at <= datetime('now')"
        )
    )
    count = result.scalar() or 0
    if count > 0:
        logger.warning("Heartbeat: found %d pending notifications to send", count)
    else:
        logger.debug("Heartbeat: no pending notifications")
    return count
