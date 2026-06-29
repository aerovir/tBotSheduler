"""Unit tests for scheduler module."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.bot.scheduler import check_pending


class TestCheckPending:
    """Test check_pending heartbeat function."""

    @staticmethod
    def _mock_bot():
        """Create a mock bot for testing."""
        bot = MagicMock()
        bot.send_message = AsyncMock(return_value=MagicMock())
        return bot

    async def test_check_pending_with_no_notifications(
        self, db_session: AsyncSession
    ):
        """Test check_pending returns 0 when no notifications exist."""
        count = await check_pending(db_session, self._mock_bot())
        assert count == 0

    async def test_check_pending_with_no_pending(
        self, db_session: AsyncSession
    ):
        """Test check_pending returns 0 when all notifications are sent."""
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

        count = await check_pending(db_session, self._mock_bot())
        assert count == 0
        # bot.send_message should NOT be called (no pending)
        bot = self._mock_bot()
        await check_pending(db_session, bot)
        bot.send_message.assert_not_awaited()

    async def test_check_pending_sends_pending(
        self, db_session: AsyncSession
    ):
        """Test check_pending sends pending notifications."""
        from datetime import date, time, datetime, timedelta

        # Insert a slot
        from tbot_sheduler.models import Slot
        from tbot_sheduler.models import Channel, Admin

        admin = Admin(user_id=9001, username="test_admin", role="owner")
        db_session.add(admin)
        await db_session.flush()

        channel = Channel(
            chat_id=-100123, title="Test Channel",
            owner_id=admin.id, booking_horizon_days=30,
        )
        db_session.add(channel)
        await db_session.flush()

        slot = Slot(
            channel_id=channel.id, date=date(2026, 6, 30),
            start_time=time(10, 0), end_time=time(11, 0),
            created_by=admin.id,
        )
        db_session.add(slot)
        await db_session.flush()

        # Insert a booking
        await db_session.execute(
            text(
                "INSERT INTO booking (slot_id, user_id, user_name, notify_minutes, created_at) "
                "VALUES (:slot_id, :user_id, :user_name, :notify_minutes, :created_at)"
            ),
            {
                "slot_id": slot.id,
                "user_id": 42,
                "user_name": "TestUser",
                "notify_minutes": 10,
                "created_at": datetime.utcnow(),
            },
        )
        await db_session.flush()

        # Insert a pending (overdue) notification
        past = datetime.utcnow() - timedelta(minutes=30)
        await db_session.execute(
            text(
                "INSERT INTO notification (booking_id, user_id, notify_at, sent, created_at) "
                "VALUES (:booking_id, :user_id, :notify_at, :sent, :created_at)"
            ),
            {
                "booking_id": 1,
                "user_id": 42,
                "notify_at": past,
                "sent": False,
                "created_at": past,
            },
        )
        await db_session.commit()

        bot = self._mock_bot()
        count = await check_pending(db_session, bot)
        assert count == 1
        bot.send_message.assert_awaited_once()
