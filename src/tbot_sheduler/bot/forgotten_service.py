"""Auto-cancel forgotten bookings — inactivity check + admin alert."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from tbot_sheduler.models import Booking, AuditLog

logger = logging.getLogger(__name__)


async def check_inactive_bookings(
    db_session: AsyncSession, bot: Bot
) -> dict:
    """Check for bookings where user has been inactive >24h before slot.

    Sends a confirmation request to the user.
    If no response within 1 hour, auto-cancels the booking.

    Returns:
        Dict with counts of checked, warned, cancelled bookings.
    """
    now = datetime.utcnow()
    inactive_cutoff = now - timedelta(hours=24)

    # Find bookings where:
    # - slot is in the future (upcoming slot, warn early)
    # - user has no other interactions >24h
    # - notification hasn't been sent yet
    result = await db_session.execute(
        text("""
            SELECT b.id, b.user_id, s.date, s.start_time
            FROM booking b
            JOIN slot s ON b.slot_id = s.id
            WHERE s.date >= date('now')
              AND b.created_at < :cutoff
              AND b.id NOT IN (
                  SELECT booking_id FROM audit_log
                  WHERE action = 'forgotten_warning'
              )
        """),
        {"cutoff": inactive_cutoff},
    )
    candidates = result.all()

    warned = 0
    for row in candidates:
        booking_id, user_id, s_date, s_time = row
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    "⏰ <b>Подтвердите бронь</b>\n\n"
                    f"У вас забронирован слот на {s_date} в {s_time}.\n"
                    "Если вы не планируете приходить — "
                    "отмените бронь, чтобы освободить слот другим.\n\n"
                    "Нажмите /confirm чтобы подтвердить.\n"
                    "Бронь будет автоматически отменена через 1 час, "
                    "если вы не ответите."
                ),
                parse_mode="HTML",
            )
            log = AuditLog(
                action="forgotten_warning",
                user_id=user_id,
                booking_id=booking_id,
                details={"date": str(s_date), "time": str(s_time)},
            )
            db_session.add(log)
            warned += 1
        except Exception as e:
            logger.error(
                "Failed to send forgotten warning for booking %d: %s",
                booking_id, e,
            )

    if warned:
        await db_session.commit()
        logger.info("Sent %d forgotten booking warnings", warned)

    # Check for warnings that expired (no confirmation within 1h)
    expire_cutoff = now - timedelta(hours=1)
    expired = await db_session.execute(
        text("""
            SELECT al.booking_id, al.user_id
            FROM audit_log al
            LEFT JOIN audit_log al2 ON al2.booking_id = al.booking_id
                AND al2.action = 'forgotten_confirmed'
            WHERE al.action = 'forgotten_warning'
              AND al.created_at < :cutoff
              AND al2.id IS NULL
        """),
        {"cutoff": expire_cutoff},
    )
    to_cancel = expired.all()

    cancelled = 0
    for booking_id, user_id in to_cancel:
        # Cancel the booking
        booking = await db_session.get(Booking, booking_id)
        if booking:
            slot_id = booking.slot_id
            await db_session.delete(booking)

            log = AuditLog(
                action="booking_cancelled",
                user_id=user_id,
                slot_id=slot_id,
                booking_id=booking_id,
                details={"cause": "auto_cancel_forgotten"},
            )
            db_session.add(log)
            cancelled += 1

    if cancelled:
        await db_session.commit()
        logger.info("Auto-cancelled %d forgotten bookings", cancelled)

    return {
        "warned": warned,
        "cancelled": cancelled,
    }


async def confirm_booking(db_session: AsyncSession, booking_id: int, user_id: int) -> dict:
    """Confirm a booking (user responded to forgotten warning)."""
    log = AuditLog(
        action="forgotten_confirmed",
        user_id=user_id,
        booking_id=booking_id,
    )
    db_session.add(log)
    await db_session.commit()
    return {"success": True}
