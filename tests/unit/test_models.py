"""Unit tests for SQLAlchemy models."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import (
    Admin, Channel, Slot, Booking, Notification, AuditLog,
)


class TestAdminModel:
    """Test Admin model creation and constraints."""

    async def test_create_admin(self, db_session: AsyncSession):
        """Test creating an admin with role."""
        admin = Admin(user_id=12345, username="test_owner", role="owner")
        db_session.add(admin)
        await db_session.commit()

        result = await db_session.execute(select(Admin).where(Admin.user_id == 12345))
        admin_db = result.scalar_one()
        assert admin_db.username == "test_owner"
        assert admin_db.role == "owner"
        assert admin_db.created_at is not None

    async def test_duplicate_user_id_raises(self, db_session: AsyncSession):
        """Test unique constraint on user_id."""
        admin1 = Admin(user_id=12345, username="admin1", role="owner")
        db_session.add(admin1)
        await db_session.commit()

        admin2 = Admin(user_id=12345, username="admin2", role="moderator")
        db_session.add(admin2)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()

    async def test_default_role(self, db_session: AsyncSession):
        """Test default role is moderator."""
        admin = Admin(user_id=99999, username="new_admin")
        db_session.add(admin)
        await db_session.commit()

        result = await db_session.execute(select(Admin).where(Admin.user_id == 99999))
        admin_db = result.scalar_one()
        assert admin_db.role == "moderator"


class TestSlotModel:
    """Test Slot model creation and constraints."""

    async def _create_owner_and_channel(
        self, db_session: AsyncSession, user_id: int, chat_id: int
    ) -> tuple[int, int]:
        """Helper to create admin + channel, return (admin_id, channel_id)."""
        admin = Admin(user_id=user_id, username="admin", role="owner")
        db_session.add(admin)
        await db_session.flush()

        channel = Channel(
            chat_id=chat_id, title="Test Channel", owner_id=admin.id
        )
        db_session.add(channel)
        await db_session.flush()

        return admin.id, channel.id

    async def test_create_slot(self, db_session: AsyncSession):
        """Test creating a slot with valid data."""
        admin_id, channel_id = await self._create_owner_and_channel(
            db_session, 111, -100123
        )

        slot = Slot(
            channel_id=channel_id,
            date=date(2026, 7, 1),
            start_time=time(10, 0),
            end_time=time(11, 0),
            created_by=admin_id,
        )
        db_session.add(slot)
        await db_session.commit()

        result = await db_session.execute(
            select(Slot).where(Slot.date == date(2026, 7, 1))
        )
        slot_db = result.scalar_one()
        assert slot_db.start_time == time(10, 0)
        assert slot_db.end_time == time(11, 0)
        assert slot_db.is_active is True

    async def test_duplicate_slot_raises(self, db_session: AsyncSession):
        """Test unique constraint on (channel_id, date, start_time)."""
        _, channel_id = await self._create_owner_and_channel(
            db_session, 222, -100456
        )

        slot1 = Slot(
            channel_id=channel_id,
            date=date(2026, 7, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        db_session.add(slot1)
        await db_session.commit()

        slot2 = Slot(
            channel_id=channel_id,
            date=date(2026, 7, 1),
            start_time=time(14, 0),
            end_time=time(15, 0),
        )
        db_session.add(slot2)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()


class TestBookingModel:
    """Test Booking model creation and constraints."""

    async def _setup_slot(
        self, db_session: AsyncSession, user_id: int, chat_id: int,
        slot_date: date = date(2026, 7, 5),
    ) -> int:
        """Create admin + channel + slot, return slot_id."""
        admin = Admin(user_id=user_id, username="admin3", role="owner")
        db_session.add(admin)
        await db_session.flush()

        channel = Channel(
            chat_id=chat_id, title="Chan", owner_id=admin.id
        )
        db_session.add(channel)
        await db_session.flush()

        slot = Slot(
            channel_id=channel.id,
            date=slot_date,
            start_time=time(9, 0),
            end_time=time(10, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        return slot.id

    async def test_create_booking_with_relations(self, db_session: AsyncSession):
        """Test creating a booking with slot relation."""
        slot_id = await self._setup_slot(db_session, 333, -100789)

        booking = Booking(
            slot_id=slot_id,
            user_id=55555,
            user_name="Test User",
            comment="Need this slot",
            notify_minutes=15,
        )
        db_session.add(booking)
        await db_session.commit()

        result = await db_session.execute(
            select(Booking).where(Booking.user_id == 55555)
        )
        booking_db = result.scalar_one()
        assert booking_db.user_name == "Test User"
        assert booking_db.notify_minutes == 15
        assert booking_db.slot_id == slot_id

    async def test_duplicate_booking_raises(self, db_session: AsyncSession):
        """Test unique constraint on (user_id, slot_id)."""
        slot_id = await self._setup_slot(
            db_session, 444, -100999, date(2026, 7, 10)
        )

        booking1 = Booking(slot_id=slot_id, user_id=77777, user_name="User")
        db_session.add(booking1)
        await db_session.commit()

        booking2 = Booking(slot_id=slot_id, user_id=77777, user_name="User2")
        db_session.add(booking2)
        with pytest.raises(Exception):
            await db_session.commit()
        await db_session.rollback()


class TestNotificationModel:
    """Test Notification model creation."""

    async def test_create_notification(self, db_session: AsyncSession):
        """Test creating a notification linked to a booking."""
        # Create prerequisites in the same session
        admin = Admin(user_id=666, username="a", role="owner")
        db_session.add(admin)
        await db_session.flush()

        channel = Channel(chat_id=-100111, title="C", owner_id=admin.id)
        db_session.add(channel)
        await db_session.flush()

        slot = Slot(
            channel_id=channel.id,
            date=date(2026, 7, 15),
            start_time=time(10, 0),
            end_time=time(11, 0),
        )
        db_session.add(slot)
        await db_session.flush()

        booking = Booking(slot_id=slot.id, user_id=88888)
        db_session.add(booking)
        await db_session.flush()

        notify_at = datetime.utcnow() + timedelta(hours=1)

        notification = Notification(
            booking_id=booking.id,
            user_id=88888,
            notify_at=notify_at,
            job_id="job_123",
        )
        db_session.add(notification)
        await db_session.commit()

        result = await db_session.execute(
            select(Notification).where(Notification.job_id == "job_123")
        )
        notif = result.scalar_one()
        assert notif.sent is False
        assert notif.user_id == 88888

    async def test_notification_index(self, db_session: AsyncSession):
        """Verify index on (notify_at, sent) exists."""
        result = await db_session.execute(
            text(
                "SELECT name FROM sqlite_master "
                "WHERE type='index' AND tbl_name='notification'"
            )
        )
        indexes = result.scalars().all()
        assert any("notify" in idx.lower() for idx in indexes)


class TestAuditLogModel:
    """Test AuditLog model creation."""

    async def test_create_audit_log(self, db_session: AsyncSession):
        """Test creating an audit log entry."""
        log = AuditLog(
            action="booking_created",
            user_id=12345,
            slot_id=1,
            booking_id=1,
            details={"notify_minutes": 10},
        )
        db_session.add(log)
        await db_session.commit()

        assert log.id is not None
        assert log.action == "booking_created"
        assert log.details == {"notify_minutes": 10}

    async def test_audit_log_json_field(self, db_session: AsyncSession):
        """Test JSON details field with complex data."""
        details = {
            "user": {"id": 123, "name": "test"},
            "changes": ["field1", "field2"],
        }
        log = AuditLog(action="booking_changed", details=details)
        db_session.add(log)
        await db_session.commit()

        result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "booking_changed")
        )
        log_db = result.scalar_one()
        assert log_db.details["user"]["name"] == "test"
        assert len(log_db.details["changes"]) == 2
