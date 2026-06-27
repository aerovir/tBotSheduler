"""Tests for forgotten booking service."""
from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import AuditLog


class TestForgottenService:
    """Test forgotten booking service."""

    async def test_confirm_booking(self, db_session: AsyncSession):
        """Test confirming a booking (response to forgotten warning)."""
        from tbot_sheduler.bot.forgotten_service import confirm_booking

        result = await confirm_booking(db_session, 1, 12345)
        assert result["success"] is True

        log = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "forgotten_confirmed")
        )
        entry = log.scalar_one()
        assert entry.user_id == 12345
        assert entry.booking_id == 1

    async def test_clean_run_with_no_candidates(self, db_session: AsyncSession):
        """Test check_inactive_bookings with no candidates."""
        from tbot_sheduler.bot.forgotten_service import check_inactive_bookings

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        result = await check_inactive_bookings(db_session, mock_bot)
        assert result["warned"] == 0
        assert result["cancelled"] == 0
        mock_bot.send_message.assert_not_called()
