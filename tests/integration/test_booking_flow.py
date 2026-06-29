"""Integration tests for booking flow."""
from __future__ import annotations

from datetime import date, time

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

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
        from tbot_sheduler.bot.booking_service import create_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        result = await create_booking(
            db_session, slot_id=slot.id, user_id=10001,
            user_name="Test User", notify_minutes=15,
        )
        assert result["success"] is True
        assert result["booking_id"] is not None

        b_result = await db_session.execute(
            select(Booking).where(Booking.user_id == 10001)
        )
        booking = b_result.scalar_one()
        assert booking.user_name == "Test User"

        a_result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "booking_created")
        )
        log = a_result.scalar_one()
        assert log.user_id == 10001

    async def test_duplicate_booking_prevented(self, db_session: AsyncSession):
        from tbot_sheduler.bot.booking_service import create_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        r1 = await create_booking(db_session, slot_id=slot.id, user_id=20001)
        assert r1["success"] is True

        r2 = await create_booking(db_session, slot_id=slot.id, user_id=20001)
        assert r2["success"] is False
        assert "уже забронировали" in r2.get("error", "")

    async def test_slot_taken_by_another(self, db_session: AsyncSession):
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
        from tbot_sheduler.bot.booking_service import create_booking, cancel_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().all()[-1]

        r1 = await create_booking(db_session, slot_id=slot.id, user_id=50001)
        booking_id = r1["booking_id"]

        r2 = await cancel_booking(db_session, booking_id, user_id=99999)
        assert r2["success"] is False

    async def test_slot_free_after_cancel(self, db_session: AsyncSession):
        """Test slot becomes available after booking is cancelled."""
        from tbot_sheduler.bot.booking_service import create_booking, cancel_booking

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        r1 = await create_booking(db_session, slot.id, user_id=55001)
        bid = r1["booking_id"]

        await cancel_booking(db_session, bid, user_id=55001)

        # Another user can now book
        r3 = await create_booking(db_session, slot.id, user_id=55002)
        assert r3["success"] is True

    async def test_change_booking(self, db_session: AsyncSession):
        """Test changing a booking to another slot."""
        from tbot_sheduler.bot.booking_service import create_booking, change_booking

        result = await db_session.execute(select(Slot))
        slots = result.scalars().all()

        r1 = await create_booking(db_session, slots[0].id, user_id=65001)
        bid = r1["booking_id"]

        r2 = await change_booking(db_session, bid, slots[2].id, user_id=65001)
        assert r2["success"] is True
        assert r2["slot_id"] == slots[2].id

        # Old slot should be free
        old_free = await create_booking(db_session, slots[0].id, user_id=65002)
        assert old_free["success"] is True

    async def test_change_booking_atomicity(self, db_session: AsyncSession):
        """Test atomicity: old booking preserved if new slot is taken."""
        from tbot_sheduler.bot.booking_service import create_booking, change_booking

        result = await db_session.execute(select(Slot))
        slots = result.scalars().all()

        # User 1 books slot[0]
        r1 = await create_booking(db_session, slots[0].id, user_id=65001)
        assert r1["success"] is True
        bid = r1["booking_id"]

        # User 2 books slot[1] — different slot
        r2 = await create_booking(db_session, slots[1].id, user_id=65002)
        assert r2["success"] is True

        # User 1 tries to change to slot[1] — already taken by user 2
        r3 = await change_booking(db_session, bid, slots[1].id, user_id=65001)
        assert r3["success"] is False
        assert "уже занят" in r3["error"]

        # User 1's original booking on slot[0] should still exist
        bookings = await db_session.execute(
            select(Booking).where(Booking.user_id == 65001)
        )
        user1_bookings = bookings.scalars().all()
        assert len(user1_bookings) == 1
        assert user1_bookings[0].slot_id == slots[0].id

        # User 2's booking on slot[1] should still exist
        bookings2 = await db_session.execute(
            select(Booking).where(Booking.user_id == 65002)
        )
        user2_bookings = bookings2.scalars().all()
        assert len(user2_bookings) == 1
        assert user2_bookings[0].slot_id == slots[1].id


class TestBookingAPI:
    """Test booking API endpoints."""

    def _make_init_data(self, user_id: int) -> str:
        import hmac, hashlib, urllib.parse, time
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": f'{{"id":{user_id},"first_name":"Test"}}',
            "auth_date": str(int(time.time())),
        }
        secret = hmac.new(b"test:fake_token_12345", b"WebAppData", hashlib.sha256).digest()
        dcs = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
        data["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
        return urllib.parse.urlencode(data)

    async def _make_app(self, db_engine, db_session):
        import time
        from fastapi import FastAPI
        app = FastAPI()
        from tbot_sheduler.api.router import api_router
        app.include_router(api_router)
        app.state.engine = db_engine
        app.state.started_at = time.monotonic()
        maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        app.state.session_maker = maker
        return app

    async def test_book_slot_api(self, db_session, db_engine):
        from httpx import AsyncClient, ASGITransport

        app = await self._make_app(db_engine, db_session)
        init_data = self._make_init_data(60001)

        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/book", json={"slot_id": slot.id, "notify_minutes": 10}, headers={"X-Init-Data": init_data})
            assert resp.status_code == 200
            assert resp.json()["success"] is True

    async def test_book_slot_api_invalid_initdata(self, db_session, db_engine):
        from httpx import AsyncClient, ASGITransport
        app = await self._make_app(db_engine, db_session)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/book", json={"slot_id": 1, "notify_minutes": 10}, headers={"X-Init-Data": "fake=1&hash=bad"})
            assert resp.status_code == 403

    async def test_cancel_via_api(self, db_session, db_engine):
        from httpx import AsyncClient, ASGITransport
        from tbot_sheduler.bot.booking_service import create_booking

        app = await self._make_app(db_engine, db_session)
        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()

        booking = await create_booking(db_session, slot.id, 70001)
        bid = booking["booking_id"]
        init_data = self._make_init_data(70001)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/cancel", json={"booking_id": bid}, headers={"X-Init-Data": init_data})
            assert resp.status_code == 200
            assert resp.json()["success"] is True

        remaining = await db_session.execute(select(Booking).where(Booking.id == bid))
        assert remaining.scalar_one_or_none() is None

    async def test_cancel_wrong_user_via_api(self, db_session, db_engine):
        from httpx import AsyncClient, ASGITransport
        from tbot_sheduler.bot.booking_service import create_booking

        app = await self._make_app(db_engine, db_session)
        result = await db_session.execute(select(Slot))
        slot = result.scalars().first()
        booking = await create_booking(db_session, slot.id, 80001)
        init_data = self._make_init_data(99999)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/cancel", json={"booking_id": booking["booking_id"]}, headers={"X-Init-Data": init_data})
            assert resp.status_code == 404

    async def test_change_via_api(self, db_session, db_engine):
        from httpx import AsyncClient, ASGITransport
        from tbot_sheduler.bot.booking_service import create_booking

        app = await self._make_app(db_engine, db_session)
        result = await db_session.execute(select(Slot))
        slots = result.scalars().all()

        booking = await create_booking(db_session, slots[0].id, 90001)
        init_data = self._make_init_data(90001)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/api/change", json={
                "booking_id": booking["booking_id"],
                "new_slot_id": slots[2].id,
                "notify_minutes": 15,
            }, headers={"X-Init-Data": init_data})
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["slot_id"] == slots[2].id
