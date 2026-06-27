"""Waiting queue service — join, leave, notify when slot free."""
from __future__ import annotations

import logging

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot

from tbot_sheduler.models import Slot, WaitingEntry

logger = logging.getLogger(__name__)


async def join_waiting(
    db_session: AsyncSession, slot_id: int, user_id: int, user_name: str | None = None
) -> dict:
    """Join waiting list for a busy slot.

    Returns:
        Dict with success status.
    """
    # Verify slot exists
    result = await db_session.execute(select(Slot).where(Slot.id == slot_id))
    slot = result.scalar_one_or_none()
    if not slot:
        return {"success": False, "error": "Слот не найден."}

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
        except Exception as e:
            logger.error(
                "Failed to notify user %d about free slot %d: %s",
                entry.user_id, slot_id, e,
            )

    # Clear waiting list
    await db_session.execute(
        delete(WaitingEntry).where(WaitingEntry.slot_id == slot_id)
    )
    await db_session.commit()

    logger.info(
        "Notified %d/%d waiting users about slot %d",
        count, len(entries), slot_id,
    )
    return count
