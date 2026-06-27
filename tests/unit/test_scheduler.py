"""Unit tests for scheduler module."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.bot.scheduler import check_pending


class TestCheckPending:
    """Test check_pending heartbeat function."""

    async def test_check_pending_with_no_notifications(
        self, db_session: AsyncSession
    ):
        """Test check_pending returns 0 when no notifications exist."""
        count = await check_pending(db_session)
        assert count == 0

    async def test_check_pending_with_no_pending(
        self, db_session: AsyncSession
    ):
        """Test check_pending returns 0 when all notifications are sent."""
        # Manually insert a sent notification
        from datetime import datetime, timedelta

        await db_session.execute(
            text(
                "INSERT INTO notification (booking_id, user_id, notify_at, sent, created_at) "
                "VALUES (:booking_id, :user_id, :notify_at, :sent, :created_at)"
            ),
            {
                "booking_id": 0,
                "user_id": 1,
                "notify_at": datetime.utcnow(),
                "sent": True,
                "created_at": datetime.utcnow(),
            },
        )
        await db_session.commit()

        count = await check_pending(db_session)
        assert count == 0
