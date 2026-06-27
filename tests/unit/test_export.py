"""Tests for schedule export."""
from __future__ import annotations

from datetime import date, time
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Admin, Channel, Slot, Booking


class TestExport:
    """Test schedule export functions."""

    async def _setup(self, db_session):
        admin = Admin(user_id=999, role="owner")
        db_session.add(admin)
        await db_session.flush()
        channel = Channel(chat_id=-100, title="Test", owner_id=admin.id)
        db_session.add(channel)
        await db_session.flush()

        slot = Slot(channel_id=channel.id, date=date(2026, 7, 20), start_time=time(10, 0), end_time=time(11, 0))
        db_session.add(slot)
        slot2 = Slot(channel_id=channel.id, date=date(2026, 7, 20), start_time=time(11, 0), end_time=time(12, 0))
        db_session.add(slot2)
        await db_session.flush()

        booking = Booking(slot_id=slot2.id, user_id=555, user_name="Test User")
        db_session.add(booking)
        await db_session.commit()

        return channel.id

    async def test_export_json(self, db_session: AsyncSession):
        from tbot_sheduler.bot.export_service import export_schedule_json
        channel_id = await self._setup(db_session)

        result = await export_schedule_json(
            db_session, channel_id,
            date(2026, 7, 1), date(2026, 7, 31),
        )
        data = json.loads(result)
        assert len(data) == 2
        assert data[0]["status"] == "available"
        assert data[1]["status"] == "booked"
        assert data[1]["booked_by"]["user_name"] == "Test User"

    async def test_export_csv(self, db_session: AsyncSession):
        from tbot_sheduler.bot.export_service import export_schedule_csv
        channel_id = await self._setup(db_session)

        result = await export_schedule_csv(
            db_session, channel_id,
            date(2026, 7, 1), date(2026, 7, 31),
        )
        assert "ID,Дата,Начало,Конец,Статус" in result
        assert "available" in result
        assert "booked" in result
        assert "Test User" in result

    async def test_export_empty(self, db_session: AsyncSession):
        from tbot_sheduler.bot.export_service import export_schedule_json, export_schedule_csv
        result = await export_schedule_json(db_session, 999, date(2026, 1, 1), date(2026, 1, 31))
        assert json.loads(result) == []

        result = await export_schedule_csv(db_session, 999, date(2026, 1, 1), date(2026, 1, 31))
        assert "ID,Дата" in result
        lines = result.strip().split("\n")
        assert len(lines) == 1  # Only header
