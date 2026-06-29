"""Notification service: JobQueue scheduling + Heartbeat delivery."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Bot
from telegram.ext import ExtBot

from tbot_sheduler.models import Booking, Slot

logger = logging.getLogger(__name__)


async def schedule_notification(
    job_queue,
    booking_id: int,
    user_id: int,
    notify_at: datetime,
    slot_date: str,
    slot_time: str,
    db_session: AsyncSession | None = None,
) -> str | None:
    """Schedule a JobQueue task for notification.

    Args:
        job_queue: Bot Application's job queue
        booking_id: Booking ID for callback data
        user_id: Telegram user ID to notify
        notify_at: When to send the notification
        slot_date: Date string for the message
        slot_time: Time string for the message
        db_session: If provided, saves job_id to Notification record.

    Returns:
        Job ID string if scheduled, None if JobQueue unavailable.
    """
    if not job_queue:
        logger.warning("JobQueue not available, notification will use heartbeat")
        return None

    now = datetime.utcnow()
    delay = max(0, (notify_at - now).total_seconds())

    job = job_queue.run_once(
        callback=_send_notification_callback,
        when=delay,
        data={
            "booking_id": booking_id,
            "user_id": user_id,
            "slot_date": slot_date,
            "slot_time": slot_time,
        },
        name=f"notify_{booking_id}",
    )

    # Save job_id to Notification record so cancel can find and remove it
    if db_session and job.name:
        try:
            await db_session.execute(
                text("UPDATE notification SET job_id = :job_id WHERE booking_id = :bid"),
                {"job_id": job.name, "bid": booking_id},
            )
            await db_session.commit()
            logger.debug(
                "Saved job_id '%s' for notification booking_id=%d",
                job.name, booking_id,
            )
        except Exception as e:
            logger.warning(
                "Failed to save job_id for booking %d: %s",
                booking_id, e,
            )

    logger.info(
        "Scheduled notification for booking %d in %.0f seconds (at %s)",
        booking_id, delay, notify_at,
    )
    return job.name


async def _send_notification_callback(context) -> None:
    """JobQueue callback: send notification to user."""
    data = context.job.data
    booking_id = data.get("booking_id")
    user_id = data.get("user_id")
    slot_date = data.get("slot_date", "")
    slot_time = data.get("slot_time", "")

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                f"⏰ <b>Напоминание о брони!</b>\n\n"
                f"📅 Дата: {slot_date}\n"
                f"🕐 Время: {slot_time}\n"
                f"Слот скоро начнётся — не опоздайте!"
            ),
            parse_mode="HTML",
        )
        logger.info(
            "JobQueue: notification sent for booking %d to user %d",
            booking_id, user_id,
        )
    except Exception as e:
        logger.error(
            "Failed to send JobQueue notification for booking %d: %s",
            booking_id, e,
        )


async def check_pending_notifications(
    db_session: AsyncSession, bot: Bot | ExtBot
) -> int:
    """Heartbeat: send pending (unsent, overdue) notifications.

    Returns:
        Number of notifications sent.
    """
    result = await db_session.execute(
        text(
            "SELECT n.id, n.booking_id, n.user_id, "
            "s.date, s.start_time, s.end_time "
            "FROM notification n "
            "JOIN booking b ON n.booking_id = b.id "
            "JOIN slot s ON b.slot_id = s.id "
            "WHERE n.sent = 0 AND n.notify_at <= datetime('now')"
        )
    )
    pending = result.all()

    sent_count = 0
    for row in pending:
        notif_id, booking_id, user_id, s_date, s_time, e_time = row
        try:
            await bot.send_message(
                chat_id=user_id,
                text=(
                    f"⏰ <b>Напоминание о брони!</b>\n\n"
                    f"📅 Дата: {s_date}\n"
                    f"🕐 Время: {s_time}–{e_time}\n"
                    f"Слот скоро начнётся — не опоздайте!"
                ),
                parse_mode="HTML",
            )
            sent_count += 1
            logger.info(
                "Heartbeat: notification sent for booking %d to user %d",
                booking_id, user_id,
            )
        except Exception as e:
            logger.error(
                "Heartbeat: failed to send notification for booking %d: %s",
                booking_id, e,
            )
            continue

        # Mark as sent regardless (avoid re-sending on next heartbeat)
        await db_session.execute(
            text("UPDATE notification SET sent = 1 WHERE id = :id"),
            {"id": notif_id},
        )

    if sent_count:
        await db_session.commit()
        logger.info(
            "Heartbeat sent %d/%d pending notifications",
            sent_count, len(pending),
        )
    else:
        logger.debug("Heartbeat: no pending notifications")

    return sent_count


async def _heartbeat_callback(context) -> None:
    """JobQueue repeating callback: periodic heartbeat check.

    Создаёт сессию из session_maker и отправляет просроченные уведомления.
    Запускается каждые 5 минут через job_queue.run_repeating.
    """
    maker = context.bot_data.get("session_maker")
    if not maker:
        logger.warning("Heartbeat callback: no session_maker in bot_data")
        return
    try:
        async with maker() as session:
            await check_pending_notifications(session, context.bot)
    except Exception as e:
        logger.error("Heartbeat callback failed: %s", e)
