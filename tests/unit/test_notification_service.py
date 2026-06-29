"""Unit tests for notification_service module."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.bot.notification_service import schedule_notification


class TestScheduleNotification:
    """Test schedule_notification function."""

    @staticmethod
    def _mock_job_queue():
        """Create a mock job queue."""
        jq = MagicMock()
        mock_job = MagicMock()
        mock_job.name = "notify_42"
        jq.run_once = MagicMock(return_value=mock_job)
        return jq

    async def test_schedule_saves_job_id(
        self, db_session: AsyncSession
    ):
        """Test that schedule_notification saves job_id to Notification."""
        # Insert a notification record first (as create_booking would)
        now = datetime.utcnow()
        await db_session.execute(
            text(
                "INSERT INTO notification (booking_id, user_id, notify_at, sent, created_at) "
                "VALUES (:booking_id, :user_id, :notify_at, :sent, :created_at)"
            ),
            {
                "booking_id": 42,
                "user_id": 1,
                "notify_at": now + timedelta(hours=1),
                "sent": False,
                "created_at": now,
            },
        )
        await db_session.commit()

        # Schedule notification with db_session
        jq = self._mock_job_queue()
        result = await schedule_notification(
            job_queue=jq,
            booking_id=42,
            user_id=1,
            notify_at=now + timedelta(hours=1),
            slot_date="2026-06-30",
            slot_time="10:00-11:00",
            db_session=db_session,
        )

        # Verify job_id was saved to notification
        assert result == "notify_42"
        row = await db_session.execute(
            text("SELECT job_id FROM notification WHERE booking_id = :bid"),
            {"bid": 42},
        )
        saved_job_id = row.scalar()
        assert saved_job_id == "notify_42"

    async def test_schedule_without_db_session(
        self, db_session: AsyncSession
    ):
        """Test schedule_notification works without db_session (no crash)."""
        now = datetime.utcnow()
        jq = self._mock_job_queue()
        result = await schedule_notification(
            job_queue=jq,
            booking_id=99,
            user_id=1,
            notify_at=now + timedelta(hours=1),
            slot_date="2026-06-30",
            slot_time="10:00-11:00",
            db_session=None,
        )
        assert result == "notify_42"

    async def test_schedule_without_job_queue(self, db_session: AsyncSession):
        """Test schedule_notification returns None when no job queue."""
        result = await schedule_notification(
            job_queue=None,
            booking_id=1,
            user_id=1,
            notify_at=datetime.utcnow(),
            slot_date="2026-06-30",
            slot_time="10:00-11:00",
            db_session=db_session,
        )
        assert result is None
