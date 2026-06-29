"""Slot management Telegram command handlers."""
from __future__ import annotations

import logging
from datetime import date, datetime, time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from tbot_sheduler.core.auth import check_role
from tbot_sheduler.core.config import WEB_APP_URL
from tbot_sheduler.core.deps import with_db
from tbot_sheduler.models import AuditLog, Channel, Slot

logger = logging.getLogger(__name__)


async def _get_channel_for_admin(
    db_session: AsyncSession, admin
) -> Channel | None:
    """Find the channel the admin (owner or moderator) has access to.

    For owners: Channel.owner_id == admin.id
    For moderators: Channel.owner_id == the owner who added them (admin.added_by)
    """
    if admin.role == "owner":
        result = await db_session.execute(
            select(Channel).where(Channel.owner_id == admin.id)
        )
    else:
        # Moderator — channel is owned by the admin who added them
        result = await db_session.execute(
            select(Channel).where(Channel.owner_id == admin.added_by)
        )
    return result.scalar_one_or_none()


async def _log_action(
    db_session: AsyncSession,
    action: str,
    user_id: int | None = None,
    slot_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Log an action to the audit log."""
    log = AuditLog(
        action=action, user_id=user_id, slot_id=slot_id, details=details
    )
    db_session.add(log)
    await db_session.commit()


@with_db
@check_role("owner", "moderator")
async def create_slots_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /create_slots — open Web App for slot creation."""
    if not WEB_APP_URL:
        await update.message.reply_text(
            "⚠️ Web App не настроен. Укажите WEB_APP_URL в .env"
        )
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📅 Создать слоты",
                web_app={"url": f"{WEB_APP_URL}/create-slots"},
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        "Нажмите кнопку ниже, чтобы создать слоты:\n\n"
        "Выберите даты и часовые интервалы.",
        reply_markup=reply_markup,
    )


@with_db
@check_role("owner", "moderator")
async def slots_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /slots — view all slots."""
    db_session: AsyncSession = context.bot_data["db"]

    user_id = update.effective_user.id
    # Find the admin's channel
    from tbot_sheduler.models import Admin

    admin_result = await db_session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin = admin_result.scalar_one_or_none()
    if not admin:
        await update.message.reply_text("⚠️ Вы не зарегистрированы как администратор.")
        return

    channel = await _get_channel_for_admin(db_session, admin)
    if not channel:
        await update.message.reply_text(
            "⚠️ Канал не настроен. Выполните /setup."
        )
        return

    # Get today's slots
    today = date.today()
    result = await db_session.execute(
        select(Slot)
        .where(
            Slot.channel_id == channel.id,
            Slot.date >= today,
            Slot.is_active == True,
        )
        .order_by(Slot.date, Slot.start_time)
        .limit(50)
    )
    slots = result.scalars().all()

    if not slots:
        await update.message.reply_text(
            "📋 Нет активных слотов.\n"
            "Используйте /create_slots чтобы создать."
        )
        return

    # Group by date
    by_date: dict[date, list[Slot]] = {}
    for slot in slots:
        if slot.date not in by_date:
            by_date[slot.date] = []
        by_date[slot.date].append(slot)

    lines = ["📋 <b>Активные слоты:</b>\n"]
    for slot_date, day_slots in sorted(by_date.items()):
        lines.append(f"<b>{slot_date.strftime('%d.%m.%Y')}:</b>")
        for s in day_slots:
            booking_status = ""
            if s.bookings:
                b = s.bookings[0]
                booking_status = f" — занято: {b.user_name or b.user_id}"
            lines.append(
                f"  🕐 {s.start_time.strftime('%H:%M')}–{s.end_time.strftime('%H:%M')}"
                f" (id: {s.id}){booking_status}"
            )
        lines.append("")

    text = "\n".join(lines)
    # Telegram limit
    if len(text) > 4000:
        text = text[:3990] + "\n..."

    await update.message.reply_text(text, parse_mode="HTML")


@with_db
@check_role("owner", "moderator")
async def free_slot_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /free_slot <id> — force free a slot by admin."""
    db_session: AsyncSession = context.bot_data["db"]
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /free_slot <id_слота>\n"
            "Пример: /free_slot 42"
        )
        return

    try:
        slot_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат ID слота.")
        return

    result = await db_session.execute(select(Slot).where(Slot.id == slot_id))
    slot = result.scalar_one_or_none()

    if not slot:
        await update.message.reply_text(f"❌ Слот с ID {slot_id} не найден.")
        return

    # Delete all bookings for this slot
    from tbot_sheduler.models import Booking

    booking_result = await db_session.execute(
        select(Booking).where(Booking.slot_id == slot_id)
    )
    for booking in booking_result.scalars():
        await db_session.delete(booking)

    slot.is_active = True
    await db_session.commit()

    await _log_action(
        db_session,
        "slot_freed",
        user_id=user_id,
        slot_id=slot_id,
        details={
            "date": str(slot.date),
            "time": f"{slot.start_time}-{slot.end_time}",
        },
    )

    await update.message.reply_text(
        f"✅ Слот #{slot_id} ({slot.date} {slot.start_time}–{slot.end_time}) "
        f"освобождён."
    )


@with_db
@check_role("owner", "moderator")
async def broadcast_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /broadcast — send booking button to channel."""
    db_session: AsyncSession = context.bot_data["db"]
    user_id = update.effective_user.id

    from tbot_sheduler.models import Admin

    admin_result = await db_session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin = admin_result.scalar_one_or_none()

    if not admin:
        await update.message.reply_text("⚠️ Вы не зарегистрированы.")
        return

    channel = await _get_channel_for_admin(db_session, admin)

    if not channel:
        await update.message.reply_text(
            "⚠️ Канал не найден. Выполните /setup сначала."
        )
        return

    if not WEB_APP_URL:
        await update.message.reply_text("⚠️ WEB_APP_URL не настроен.")
        return

    keyboard = [
        [
            InlineKeyboardButton(
                "📅 Забронировать",
                web_app={"url": f"{WEB_APP_URL}/book"},
            )
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    try:
        await context.bot.send_message(
            chat_id=channel.chat_id,
            text=(
                "📅 <b>Бронирование расписания</b>\n\n"
                "Нажмите кнопку ниже, чтобы выбрать и забронировать слот."
            ),
            reply_markup=reply_markup,
            parse_mode="HTML",
        )
        await update.message.reply_text("✅ Сообщение с кнопкой опубликовано в канале.")
        logger.info(
            "Broadcast sent to channel %s by user %d", channel.chat_id, user_id
        )

        await _log_action(
            db_session,
            "broadcast_sent",
            user_id=user_id,
            details={"channel_id": channel.chat_id},
        )
    except Exception as e:
        logger.error("Broadcast failed: %s", e)
        await update.message.reply_text(
            "⚠️ Не удалось отправить сообщение в канал. "
            "Убедитесь, что бот добавлен в канал."
        )
