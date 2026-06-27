"""Tests for waiting queue."""
from __future__ import annotations

from datetime import date, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Admin, Channel, Slot, WaitingEntry


class TestWaitingQueue:
    """Test waiting queue model."""

    async def _setup(self, db_session):
        admin = Admin(user_id=101, role="owner")
        db_session.add(admin)
        await db_session.flush()
        channel = Channel(chat_id=-1001, title="Test", owner_id=admin.id)
        db_session.add(channel)
        await db_session.flush()
        slot = Slot(channel_id=channel.id, date=date(2026, 8, 1), start_time=time(10, 0), end_time=time(11, 0))
        db_session.add(slot)
        await db_session.commit()
        return slot.id

    async def test_create_waiting_entry(self, db_session: AsyncSession):
        slot_id = await self._setup(db_session)
        entry = WaitingEntry(slot_id=slot_id, user_id=111, user_name="Waiter")
        db_session.add(entry)
        await db_session.commit()

        result = await db_session.execute(
            select(WaitingEntry).where(WaitingEntry.user_id == 111)
        )
        entry_db = result.scalar_one()
        assert entry_db.slot_id == slot_id
        assert entry_db.user_name == "Waiter"

    async def test_unique_constraint(self, db_session: AsyncSession):
        slot_id = await self._setup(db_session)
        entry1 = WaitingEntry(slot_id=slot_id, user_id=222)
        db_session.add(entry1)
        await db_session.commit()

        import pytest
        entry2 = WaitingEntry(slot_id=slot_id, user_id=222)
        db_session.add(entry2)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()

    async def test_get_waiting_list(self, db_session: AsyncSession):
        slot_id = await self._setup(db_session)
        for uid in [333, 444, 555]:
            db_session.add(WaitingEntry(slot_id=slot_id, user_id=uid))
        await db_session.commit()

        result = await db_session.execute(
            select(WaitingEntry).where(WaitingEntry.slot_id == slot_id)
        )
        entries = result.scalars().all()
        assert len(entries) == 3
