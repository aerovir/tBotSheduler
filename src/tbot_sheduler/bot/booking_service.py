"""Booking logic: create, cancel, check availability."""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import exc, select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Booking, Slot, AuditLog, Notification

logger = logging.getLogger(__name__)


async def get_available_slots(
    db_session: AsyncSession, channel_id: int, target_date: date
) -> list[dict[str, Any]]:
    """Get available (unbooked) slots for a given channel and date."""
    result = await db_session.execute(
        select(Slot).where(
            Slot.channel_id == channel_id,
            Slot.date == target_date,
            Slot.is_active == True,
        ).order_by(Slot.start_time)
    )
    slots = result.scalars().all()

    available = []
    for slot in slots:
        bookings_count = len(slot.bookings)
        available.append({
            "id": slot.id,
            "date": str(slot.date),
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "available": bookings_count == 0,
        })

    return available


async def create_booking(
    db_session: AsyncSession,
    slot_id: int,
    user_id: int,
    user_name: str | None = None,
    comment: str | None = None,
    notify_minutes: int = 10,
) -> dict[str, Any]:
    """Create a booking.

    Race condition protection via:
    - UniqueConstraint (user_id, slot_id) — предотвращает двойной клик
    - UniqueConstraint (slot_id) — предотвращает двойную бронь разными пользователями
    - IntegrityError перехватывается и возвращает ошибку

    Returns:
        Dict with booking info or error.
    """
    # Verify slot exists and is active
    result = await db_session.execute(
        select(Slot).where(Slot.id == slot_id)
    )
    slot = result.scalar_one_or_none()

    if not slot:
        return {"success": False, "error": "Слот не найден."}

    if not slot.is_active:
        return {"success": False, "error": "Слот неактивен."}

    # Check if already booked by this user (локальная проверка до INSERT)
    existing = await db_session.execute(
        select(Booking).where(
            Booking.slot_id == slot_id,
            Booking.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return {
            "success": False,
            "error": "Вы уже забронировали этот слот.",
        }

    # Create booking (БД гарантирует уникальность slot_id через uq_booking_slot)
    try:
        booking = Booking(
            slot_id=slot_id,
            user_id=user_id,
            user_name=user_name,
            comment=comment,
            notify_minutes=notify_minutes,
        )
        db_session.add(booking)
        await db_session.flush()

        # Create notification record
        slot_datetime = datetime.combine(slot.date, slot.start_time)
        notify_at = slot_datetime - timedelta(minutes=notify_minutes)

        notification = Notification(
            booking_id=booking.id,
            user_id=user_id,
            notify_at=notify_at,
            sent=False,
        )
        db_session.add(notification)
        await db_session.flush()

        # Audit log
        log = AuditLog(
            action="booking_created",
            user_id=user_id,
            slot_id=slot_id,
            booking_id=booking.id,
            details={"notify_minutes": notify_minutes},
        )
        db_session.add(log)

        await db_session.commit()
    except exc.IntegrityError:
        await db_session.rollback()
        logger.warning(
            "Race condition: slot %d double-booked by user %d (IntegrityError)",
            slot_id, user_id,
        )
        return {
            "success": False,
            "error": "Этот слот уже занят.",
        }

    return {
        "success": True,
        "booking_id": booking.id,
        "slot_id": slot_id,
        "date": str(slot.date),
        "start_time": slot.start_time.strftime("%H:%M"),
        "end_time": slot.end_time.strftime("%H:%M"),
        "notify_at": notify_at.isoformat(),
    }


async def cancel_booking(
    db_session: AsyncSession,
    booking_id: int,
    user_id: int,
) -> dict[str, Any]:
    """Cancel a booking by its ID.

    Returns:
        Dict with success status and info.
    """
    result = await db_session.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    booking = result.scalar_one_or_none()

    if not booking:
        return {"success": False, "error": "Бронь не найдена."}

    if booking.user_id != user_id:
        return {
            "success": False,
            "error": "Вы не можете отменить чужую бронь.",
        }

    slot_id = booking.slot_id
    old_job_id = None

    # Find existing notification job_id
    notif_result = await db_session.execute(
        select(Notification).where(Notification.booking_id == booking_id)
    )
    notification = notif_result.scalar_one_or_none()
    if notification:
        old_job_id = notification.job_id

    # Audit log
    log = AuditLog(
        action="booking_cancelled",
        user_id=user_id,
        slot_id=slot_id,
        booking_id=booking_id,
        details={"cause": "user"},
    )
    db_session.add(log)

    # Delete booking (cascades to notifications)
    await db_session.delete(booking)
    await db_session.commit()

    return {
        "success": True,
        "slot_id": slot_id,
        "removed_job_id": old_job_id,
    }


async def change_booking(
    db_session: AsyncSession,
    booking_id: int,
    new_slot_id: int,
    user_id: int,
    notify_minutes: int = 10,
    comment: str | None = None,
) -> dict[str, Any]:
    """Change a booking to a different slot.

    Вся операция в одной транзакции: delete + insert в рамках одного commit'а.
    Если новый слот занят или произошла ошибка — всё откатывается,
    старая бронь сохраняется.

    Returns:
        Dict with new booking info or error.
    """
    # 1. Verify new slot exists, is active, and is free
    slot_result = await db_session.execute(
        select(Slot).where(Slot.id == new_slot_id)
    )
    new_slot = slot_result.scalar_one_or_none()
    if not new_slot:
        return {"success": False, "error": "Новый слот не найден."}
    if not new_slot.is_active:
        return {"success": False, "error": "Новый слот неактивен."}

    # Check that new slot isn't booked by anyone else
    existing = await db_session.execute(
        select(Booking).where(Booking.slot_id == new_slot_id)
    )
    if existing.scalar_one_or_none():
        return {"success": False, "error": "Этот слот уже занят."}

    # 2. Find old booking
    old_booking_result = await db_session.execute(
        select(Booking).where(Booking.id == booking_id)
    )
    old_booking = old_booking_result.scalar_one_or_none()
    if not old_booking:
        return {"success": False, "error": "Бронь не найдена."}
    if old_booking.user_id != user_id:
        return {"success": False, "error": "Вы не можете изменить чужую бронь."}

    old_slot_id = old_booking.slot_id
    user_name = old_booking.user_name
    # Preserve comment from old booking unless a new one is provided
    effective_comment = comment if comment is not None else old_booking.comment

    # 3. Atomically: delete old booking, create new booking, log audit
    try:
        # Delete old notification
        notif_result = await db_session.execute(
            select(Notification).where(Notification.booking_id == booking_id)
        )
        old_notification = notif_result.scalar_one_or_none()
        if old_notification:
            await db_session.delete(old_notification)

        # Delete old booking
        await db_session.delete(old_booking)

        # Create new booking
        new_booking = Booking(
            slot_id=new_slot_id,
            user_id=user_id,
            user_name=user_name,
            comment=effective_comment,
            notify_minutes=notify_minutes,
        )
        db_session.add(new_booking)
        await db_session.flush()

        # Create new notification
        slot_datetime = datetime.combine(new_slot.date, new_slot.start_time)
        notify_at = slot_datetime - timedelta(minutes=notify_minutes)
        notification = Notification(
            booking_id=new_booking.id,
            user_id=user_id,
            notify_at=notify_at,
            sent=False,
        )
        db_session.add(notification)
        await db_session.flush()

        # Audit log
        log = AuditLog(
            action="booking_changed",
            user_id=user_id,
            slot_id=new_slot_id,
            booking_id=new_booking.id,
            details={
                "old_slot_id": old_slot_id,
                "old_booking_id": booking_id,
                "new_slot_id": new_slot_id,
                "notify_minutes": notify_minutes,
            },
        )
        db_session.add(log)

        await db_session.commit()
    except exc.IntegrityError:
        await db_session.rollback()
        logger.warning(
            "change_booking: IntegrityError — new slot %d taken, old booking %d preserved",
            new_slot_id, booking_id,
        )
        return {
            "success": False,
            "error": "Этот слот уже занят.",
        }

    return {
        "success": True,
        "booking_id": new_booking.id,
        "slot_id": new_slot_id,
        "old_booking_id": booking_id,
        "old_slot_id": old_slot_id,
        "date": str(new_slot.date),
        "start_time": new_slot.start_time.strftime("%H:%M"),
        "end_time": new_slot.end_time.strftime("%H:%M"),
        "notify_at": notify_at.isoformat(),
    }


async def get_user_bookings(
    db_session: AsyncSession, user_id: int
) -> list[dict[str, Any]]:
    """Get all bookings for a user with slot info."""
    result = await db_session.execute(
        select(Booking).where(Booking.user_id == user_id).order_by(Booking.created_at.desc())
    )
    bookings = result.scalars().all()

    output = []
    for booking in bookings:
        slot = await db_session.get(Slot, booking.slot_id)
        output.append({
            "booking_id": booking.id,
            "slot_id": booking.slot_id,
            "date": str(slot.date) if slot else "N/A",
            "start_time": slot.start_time.strftime("%H:%M") if slot else "N/A",
            "end_time": slot.end_time.strftime("%H:%M") if slot else "N/A",
            "comment": booking.comment,
            "notify_minutes": booking.notify_minutes,
            "created_at": booking.created_at.isoformat() if booking.created_at else "",
        })

    return output
