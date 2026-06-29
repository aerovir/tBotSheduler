"""Booking API endpoints for Telegram Web App."""
from __future__ import annotations

import json
import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.bot.booking_service import (
    create_booking,
    cancel_booking,
    change_booking,
    get_available_slots,
    get_user_bookings,
)
from tbot_sheduler.core.config import BOT_TOKEN
from tbot_sheduler.core.deps import get_db
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


class ChangeRequest(BaseModel):
    """Booking change request."""
    booking_id: int
    new_slot_id: int
    notify_minutes: int = 10


def _verify_init_data(init_data: str, max_age_seconds: int = 86400) -> int:
    """Verify initData and return user_id.

    Args:
        init_data: Raw initData string from Telegram.WebApp.initData
        max_age_seconds: Maximum age of auth_date (300 for writes, 86400 for reads)

    Returns:
        Telegram user_id from the verified initData

    Raises:
        HTTPException(403): If initData is invalid or expired
    """
    parsed = validate_init_data(init_data, BOT_TOKEN, max_age_seconds=max_age_seconds)
    if not parsed:
        raise HTTPException(status_code=403, detail="Invalid or expired initData")

    try:
        user_data = json.loads(parsed.get("user", "{}"))
        user_id = int(user_data.get("id", 0))
    except (json.JSONDecodeError, ValueError, TypeError):
        raise HTTPException(status_code=403, detail="Invalid user data")

    if not user_id:
        raise HTTPException(status_code=403, detail="User ID not found")

    return user_id


def _get_user_name(init_data: str, max_age_seconds: int = 86400) -> str | None:
    """Extract user name from initData."""
    parsed = validate_init_data(init_data, BOT_TOKEN, max_age_seconds=max_age_seconds)
    if not parsed:
        return None
    try:
        user_data = json.loads(parsed.get("user", "{}"))
        name = user_data.get("first_name", "")
        if user_data.get("last_name"):
            name += f" {user_data['last_name']}"
        return name or None
    except (json.JSONDecodeError, ValueError):
        return None


@router.get("/book/slots")
async def list_slots(
    request: Request, channel_id: int, date_str: str,
    db_session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get available slots for a channel and date."""
    init_data = request.headers.get("X-Init-Data", "")
    _verify_init_data(init_data)

    try:
        target_date = date.fromisoformat(date_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format")

    return await get_available_slots(db_session, channel_id, target_date)


@router.post("/book")
async def book_slot(
    request: Request, body: BookingRequest,
    db_session: AsyncSession = Depends(get_db),
) -> dict:
    """Book a slot."""
    init_data = request.headers.get("X-Init-Data", "")
    user_id = _verify_init_data(init_data, max_age_seconds=300)

    if not anti_flood.check(user_id):
        raise HTTPException(
            status_code=429,
            detail="Слишком часто. Попробуйте через 5 секунд.",
        )

    user_name = _get_user_name(init_data, max_age_seconds=300)

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

    # Schedule JobQueue notification
    try:
        from tbot_sheduler.bot.notification_service import schedule_notification
        from datetime import datetime

        job_queue = request.app.state.bot_app.job_queue if hasattr(request.app.state, 'bot_app') else None
        if job_queue:
            notify_at = datetime.fromisoformat(result.get("notify_at", ""))
            await schedule_notification(
                job_queue=job_queue,
                booking_id=result["booking_id"],
                user_id=user_id,
                notify_at=notify_at,
                slot_date=result.get("date", ""),
                slot_time=f"{result.get('start_time', '')}-{result.get('end_time', '')}",
                db_session=db_session,
            )
    except Exception as e:
        logger.error("Failed to schedule notification: %s", e)

    return result


@router.get("/my-bookings")
async def my_bookings(
    request: Request,
    db_session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Get current user's bookings."""
    init_data = request.headers.get("X-Init-Data", "")
    user_id = _verify_init_data(init_data)

    return await get_user_bookings(db_session, user_id)


@router.post("/cancel")
async def cancel_book(
    request: Request, body: CancelRequest,
    db_session: AsyncSession = Depends(get_db),
) -> dict:
    """Cancel a booking."""
    init_data = request.headers.get("X-Init-Data", "")
    user_id = _verify_init_data(init_data, max_age_seconds=300)

    if not anti_flood.check(user_id):
        raise HTTPException(
            status_code=429,
            detail="Слишком часто. Попробуйте через 5 секунд.",
        )

    result = await cancel_booking(db_session, body.booking_id, user_id)

    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["error"])

    # Remove JobQueue task if exists
    removed_job_id = result.get("removed_job_id")
    if removed_job_id:
        try:
            bot_app = getattr(request.app.state, 'bot_app', None)
            if bot_app and bot_app.job_queue:
                bot_app.job_queue.scheduler.remove_job(removed_job_id)
                logger.info("Removed JobQueue task %s for cancelled booking", removed_job_id)
        except Exception as e:
            logger.warning("Could not remove JobQueue task %s: %s", removed_job_id, e)

    return {"success": True, "slot_id": result["slot_id"]}


@router.post("/change")
async def change_book(
    request: Request, body: ChangeRequest,
    db_session: AsyncSession = Depends(get_db),
) -> dict:
    """Change a booking to a different slot."""
    init_data = request.headers.get("X-Init-Data", "")
    user_id = _verify_init_data(init_data, max_age_seconds=300)

    if not anti_flood.check(user_id):
        raise HTTPException(
            status_code=429,
            detail="Слишком часто. Попробуйте через 5 секунд.",
        )

    result = await change_booking(
        db_session, body.booking_id, body.new_slot_id, user_id, body.notify_minutes,
    )

    if not result["success"]:
        raise HTTPException(status_code=409, detail=result["error"])

    # Schedule new JobQueue notification
    try:
        from tbot_sheduler.bot.notification_service import schedule_notification
        from datetime import datetime

        job_queue = request.app.state.bot_app.job_queue if hasattr(request.app.state, 'bot_app') else None
        if job_queue and result.get("notify_at"):
            notify_at = datetime.fromisoformat(result["notify_at"])
            await schedule_notification(
                job_queue=job_queue,
                booking_id=result["booking_id"],
                user_id=user_id,
                notify_at=notify_at,
                slot_date=result.get("date", ""),
                slot_time=f"{result.get('start_time', '')}-{result.get('end_time', '')}",
                db_session=db_session,
            )
    except Exception as e:
        logger.error("Failed to reschedule notification after change: %s", e)

    return result
