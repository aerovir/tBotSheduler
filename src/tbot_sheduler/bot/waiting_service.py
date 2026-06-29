"""Waiting queue service — join, leave, notify when slot free."""
from __future__ import annotations

import logging

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from tbot_sheduler.models import Booking, Slot, WaitingEntry

logger = logging.getLogger(__name__)


async def join_waiting(
    db_session: AsyncSession, slot_id: int, user_id: int, user_name: str | None = None
) -> dict:
    """Join waiting list for a busy slot.

    Проверяет, что слот существует и занят (есть активная бронь).

    Returns:
        Dict with success status.
    """
    # Verify slot exists
    result = await db_session.execute(select(Slot).where(Slot.id == slot_id))
    slot = result.scalar_one_or_none()
    if not slot:
        return {"success": False, "error": "Слот не найден."}

    # Check slot is actually busy (has a booking)
    booking_result = await db_session.execute(
        select(Booking).where(Booking.slot_id == slot_id)
    )
    if not booking_result.scalar_one_or_none():
        return {"success": False, "error": "Слот свободен, можете забронировать сразу."}

    # Check if already in waiting list
    existing = await db_session.execute(
        select(WaitingEntry).where(
            WaitingEntry.slot_id == slot_id,
            WaitingEntry.user_id == user_id,
        )
    )
    if existing.scalar_one_or_none():
        return {"success": False, "error": "Вы уже в списке ожидания."}

    entry = WaitingEntry(slot_id=slot_id, user_id=user_id, user_name=user_name)
    db_session.add(entry)
    await db_session.commit()

    logger.info("User %d joined waiting list for slot %d", user_id, slot_id)
    return {"success": True}


async def leave_waiting(
    db_session: AsyncSession, slot_id: int, user_id: int
) -> dict:
    """Leave waiting list."""
    await db_session.execute(
        delete(WaitingEntry).where(
            WaitingEntry.slot_id == slot_id,
            WaitingEntry.user_id == user_id,
        )
    )
    await db_session.commit()
    return {"success": True}


async def notify_waiting_users(
    db_session: AsyncSession, slot_id: int, bot: Bot
) -> int:
    """Notify all waiting users that slot is free.

    Called when a booking is cancelled.

    Returns:
        Number of notified users.
    """
    result = await db_session.execute(
        select(WaitingEntry).where(WaitingEntry.slot_id == slot_id)
    )
    entries = result.scalars().all()

    if not entries:
        return 0

    count = 0
    notified_ids: list[int] = []
    for entry in entries:
        try:
            await bot.send_message(
                chat_id=entry.user_id,
                text=(
                    "🎉 <b>Слот освободился!</b>\n\n"
                    "Слот, на который вы ожидали, снова свободен.\n"
                    "Поспешите забронировать!"
                ),
                parse_mode="HTML",
            )
            count += 1
            notified_ids.append(entry.id)
        except Exception as e:
            logger.error(
                "Failed to notify user %d about free slot %d: %s",
                entry.user_id, slot_id, e,
            )

    # Clear only successfully notified users
    if notified_ids:
        await db_session.execute(
            delete(WaitingEntry).where(
                WaitingEntry.slot_id == slot_id,
                WaitingEntry.id.in_(notified_ids),
            )
        )
        await db_session.commit()
        logger.info(
            "Notified %d/%d waiting users about slot %d, removed %d from queue",
            count, len(entries), slot_id, len(notified_ids),
        )
    else:
        logger.warning(
            "Failed to notify any of %d waiting users for slot %d, queue preserved",
            len(entries), slot_id,
        )
    return count
