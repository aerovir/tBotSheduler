"""Integration tests for booking flow."""
from __future__ import annotations

from datetime import date, time

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Admin, Channel, Slot, Booking, Notification, AuditLog


@pytest_asyncio.fixture(autouse=True)
async def _setup_channel(db_session):
    """Create admin + channel + some slots for testing."""
    from tbot_sheduler.core.auth import _role_cache
    _role_cache.clear()
    admin = Admin(user_id=9001, role="owner")
    db_session.add(admin)
    await db_session.flush()

    channel = Channel(chat_id=-1009999, title="Test Channel", owner_id=admin.id)
    db_session.add(channel)
    await db_session.flush()

    for i, h in enumerate([10, 11, 14]):
        slot = Slot(
            channel_id=channel.id,
            date=date(2026, 7, 15),
            start_time=time(h, 0),
            end_time=time(h + 1, 0),
        )
        db_session.add(slot)
    await db_session.commit()
    _role_cache.clear()


class TestBookingService:
    """Test booking service functions."""

    async def test_create_booking(self, db_session: AsyncSession):
        """Test creating a booking."""
        from tbot_sheduler.bot.booking_service import create_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        result = await create_booking(
            db_session, slot_id=slot.id, user_id=10001,
            user_name="Test User", notify_minutes=15,
        )
        assert result["success"] is True
        assert result["booking_id"] is not None
        assert result["slot_id"] == slot.id

        b_result = await db_session.execute(
            select(Booking).where(Booking.user_id == 10001)
        )
        booking = b_result.scalar_one()
        assert booking.user_name == "Test User"
        assert booking.notify_minutes == 15

        n_result = await db_session.execute(
            select(Notification).where(Notification.booking_id == booking.id)
        )
        notif = n_result.scalar_one()
        assert notif.sent is False

        a_result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "booking_created")
        )
        log = a_result.scalar_one()
        assert log.user_id == 10001

    async def test_duplicate_booking_prevented(self, db_session: AsyncSession):
        """Test duplicate booking (same user, same slot) is prevented."""
        from tbot_sheduler.bot.booking_service import create_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        r1 = await create_booking(db_session, slot_id=slot.id, user_id=20001)
        assert r1["success"] is True

        r2 = await create_booking(db_session, slot_id=slot.id, user_id=20001)
        assert r2["success"] is False
        assert "уже забронировали" in r2.get("error", "")

    async def test_slot_taken_by_another(self, db_session: AsyncSession):
        """Test slot taken by another user is rejected."""
        from tbot_sheduler.bot.booking_service import create_booking

        result = await db_session.execute(select(Slot))
        slots = result.scalars().all()
        slot = slots[1]

        r1 = await create_booking(db_session, slot_id=slot.id, user_id=30001)
        assert r1["success"] is True

        r2 = await create_booking(db_session, slot_id=slot.id, user_id=30002)
        assert r2["success"] is False
        assert "уже занят" in r2.get("error", "")

    async def test_cancel_booking(self, db_session: AsyncSession):
        """Test cancelling a booking."""
        from tbot_sheduler.bot.booking_service import create_booking, cancel_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().all()[-1]

        r1 = await create_booking(db_session, slot_id=slot.id, user_id=40001)
        booking_id = r1["booking_id"]

        r2 = await cancel_booking(db_session, booking_id, user_id=40001)
        assert r2["success"] is True

        b_result = await db_session.execute(
            select(Booking).where(Booking.id == booking_id)
        )
        assert b_result.scalar_one_or_none() is None

    async def test_cancel_wrong_user(self, db_session: AsyncSession):
        """Test cancelling another user's booking fails."""
        from tbot_sheduler.bot.booking_service import create_booking, cancel_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().all()[-1]

        r1 = await create_booking(db_session, slot_id=slot.id, user_id=50001)
        booking_id = r1["booking_id"]

        r2 = await cancel_booking(db_session, booking_id, user_id=99999)
        assert r2["success"] is False


class TestBookingAPI:
    """Test booking API endpoints."""

    async def test_book_slot_api(self, db_session, db_engine):
        """Test booking via API endpoint."""
        import hmac, hashlib, urllib.parse, time
        from httpx import AsyncClient, ASGITransport
        from fastapi import FastAPI

        app = FastAPI()
        from tbot_sheduler.api.router import api_router
        app.include_router(api_router)
        app.state.engine = db_engine
        app.state.started_at = time.monotonic()
        app.state.db_session = db_session

        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":60001,"first_name":"Test"}',
            "auth_date": str(int(time.time())),
        }
        secret = hmac.new(b"WebAppData", b"test:fake_token_12345", hashlib.sha256).digest()
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        init_data = urllib.parse.urlencode(data)

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/book",
                json={"slot_id": slot.id, "notify_minutes": 10},
                headers={"X-Init-Data": init_data},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    async def test_book_slot_api_invalid_initdata(self, db_session, db_engine):
        """Test booking with invalid initData returns 403."""
        import time
        from httpx import AsyncClient, ASGITransport
        from fastapi import FastAPI

        app = FastAPI()
        from tbot_sheduler.api.router import api_router
        app.include_router(api_router)
        app.state.engine = db_engine
        app.state.started_at = time.monotonic()
        app.state.db_session = db_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/api/book",
                json={"slot_id": 1, "notify_minutes": 10},
                headers={"X-Init-Data": "fake=1&hash=bad"},
            )
            assert response.status_code == 403
