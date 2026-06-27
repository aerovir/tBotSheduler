"""Booking API endpoints for Telegram Web App."""
from __future__ import annotations

import json
import logging
from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from tbot_sheduler.bot.booking_service import (
    create_booking,
    get_available_slots,
    get_user_bookings,
)
from tbot_sheduler.core.config import BOT_TOKEN
from tbot_sheduler.core.security import anti_flood, validate_init_data

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["booking"])


class BookingRequest(BaseModel):
    """Booking creation request from Web App."""
    slot_id: int
    notify_minutes: int = 10
    comment: str | None = None


class CancelRequest(BaseModel):
    """Booking cancellation request."""
    booking_id: int


def _verify_init_data(init_data: str) -> int:
    """Verify initData and return user_id. Raises HTTPException on failure."""
    parsed = validate_init_data(init_data, BOT_TOKEN)
    if not parsed:
        raise HTTPException(status_code=403, detail="Invalid initData")

    try:
        user_data = json.loads(parsed.get("user", "{}"))
        user_id = int(user_data.get("id", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Invalid user data")

    if not user_id:
        raise HTTPException(status_code=403, detail="User ID not found")

    return user_id


@router.get("/book/slots")
async def list_slots(
    request: Request, channel_id: int, date_str: str
) -> list[dict]:
    """Get available slots for a channel and date.

    Requires valid initData in X-Init-Data header.
    """
    init_data = request.headers.get("X-Init-Data", "")
    _verify_init_data(init_data)

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    db_session = request.app.state.db_session
    slots = await get_available_slots(db_session, channel_id, target_date)
    return slots


@router.post("/book")
async def book_slot(
    request: Request, body: BookingRequest
) -> dict:
    """Book a slot.

    Requires valid initData in X-Init-Data header.
    """
    init_data = request.headers.get("X-Init-Data", "")
    user_id = _verify_init_data(init_data)

    # Anti-flood check
    if not anti_flood.check(user_id):
        raise HTTPException(
            status_code=429,
            detail="Слишком часто. Попробуйте через 5 секунд.",
        )

    db_session = request.app.state.db_session

    # Parse user name from initData
    user_name = None
    try:
        parsed = validate_init_data(init_data, BOT_TOKEN)
        if parsed:
            user_data = json.loads(parsed.get("user", "{}"))
            user_name = user_data.get("first_name", "")
            if user_data.get("last_name"):
                user_name += f" {user_data['last_name']}"
    except (json.JSONDecodeError, ValueError):
        pass

    result = await create_booking(
        db_session=db_session,
        slot_id=body.slot_id,
        user_id=user_id,
        user_name=user_name,
        comment=body.comment,
        notify_minutes=body.notify_minutes,
    )

    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["error"])

    return result


@router.get("/my-bookings")
async def my_bookings(request: Request) -> list[dict]:
    """Get current user's bookings.

    Requires valid initData in X-Init-Data header.
    """
    init_data = request.headers.get("X-Init-Data", "")
    user_id = _verify_init_data(init_data)

    db_session = request.app.state.db_session
    bookings = await get_user_bookings(db_session, user_id)
    return bookings
