"""Tests for waiting queue service."""
from __future__ import annotations

from datetime import date, time
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Admin, Channel, Slot, WaitingEntry


class TestWaitingQueueService:
    """Test waiting queue service."""

    async def _setup(self, db_session):
        admin = Admin(user_id=101, role="owner")
        db_session.add(admin)
        await db_session.flush()
        channel = Channel(chat_id=-1001, title="Test", owner_id=admin.id)
        db_session.add(channel)
        await db_session.flush()
        slot = Slot(
            channel_id=channel.id, date=date(2026, 8, 1),
            start_time=time(10, 0), end_time=time(11, 0),
        )
        db_session.add(slot)
        await db_session.commit()
        return slot.id, channel.id

    async def test_join_waiting(self, db_session: AsyncSession):
        from tbot_sheduler.bot.waiting_service import join_waiting
        slot_id, _ = await self._setup(db_session)

        result = await join_waiting(db_session, slot_id, 1001, "User1")
        assert result["success"] is True

        entry = await db_session.execute(
            select(WaitingEntry).where(WaitingEntry.user_id == 1001)
        )
        assert entry.scalar_one() is not None

    async def test_join_duplicate(self, db_session: AsyncSession):
        from tbot_sheduler.bot.waiting_service import join_waiting
        slot_id, _ = await self._setup(db_session)

        await join_waiting(db_session, slot_id, 2001)
        result = await join_waiting(db_session, slot_id, 2001)
        assert result["success"] is False
        assert "уже в списке" in result.get("error", "")

    async def test_leave_waiting(self, db_session: AsyncSession):
        from tbot_sheduler.bot.waiting_service import join_waiting, leave_waiting
        slot_id, _ = await self._setup(db_session)

        await join_waiting(db_session, slot_id, 3001)
        result = await leave_waiting(db_session, slot_id, 3001)
        assert result["success"] is True

        entry = await db_session.execute(
            select(WaitingEntry).where(WaitingEntry.user_id == 3001)
        )
        assert entry.scalar_one_or_none() is None

    async def test_notify_waiting(self, db_session: AsyncSession):
        from tbot_sheduler.bot.waiting_service import join_waiting, notify_waiting_users
        slot_id, _ = await self._setup(db_session)

        await join_waiting(db_session, slot_id, 4001, "UserA")
        await join_waiting(db_session, slot_id, 4002, "UserB")

        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()

        count = await notify_waiting_users(db_session, slot_id, mock_bot)
        assert count == 2
        assert mock_bot.send_message.call_count == 2

        # Waiting list should be cleared
        entries = await db_session.execute(
            select(WaitingEntry).where(WaitingEntry.slot_id == slot_id)
        )
        assert len(entries.scalars().all()) == 0
