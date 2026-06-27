"""Admin and moderation Telegram command handlers."""
from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from tbot_sheduler.core.auth import check_admin, check_role, user_has_role
from tbot_sheduler.models import Admin, AuditLog, Channel

logger = logging.getLogger(__name__)


async def _log_action(
    db_session: AsyncSession,
    action: str,
    user_id: int | None = None,
    details: dict | None = None,
) -> None:
    """Log an action to the audit log."""
    log = AuditLog(action=action, user_id=user_id, details=details)
    db_session.add(log)
    await db_session.commit()
    logger.info("AuditLog: %s (user=%s, details=%s)", action, user_id, details)


async def setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /setup — bind bot to a channel, creator becomes owner."""
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.full_name
    db_session: AsyncSession = context.bot_data["db_session"]

    # Check if already admin
    if await user_has_role(db_session, user_id, ["owner", "moderator", "developer"]):
        await update.message.reply_text(
            "ℹ️ Вы уже являетесь администратором бота."
        )
        return

    # Get chat info
    chat = update.effective_chat
    if chat.type == "private":
        await update.message.reply_text(
            "ℹ️ Эта команда работает только в канале или группе.\n"
            "Добавьте бота в канал и выполните /setup там."
        )
        return

    # Create owner admin
    admin = Admin(
        user_id=user_id,
        username=username,
        role="owner",
    )
    db_session.add(admin)
    await db_session.commit()

    # Create channel record
    channel = Channel(
        chat_id=chat.id,
        title=chat.title or "Untitled",
        owner_id=admin.id,
    )
    db_session.add(channel)
    await db_session.commit()

    await _log_action(
        db_session, "setup_completed",
        user_id=user_id,
        details={"chat_id": chat.id, "chat_title": chat.title},
    )

    logger.info("Setup completed: user %d is owner of chat %d", user_id, chat.id)
    await update.message.reply_text(
        "✅ Бот настроен! Вы стали владельцем (owner) этого канала.\n\n"
        "Теперь вы можете:\n"
        "• /create_slots — создать слоты для бронирования\n"
        "• /add_moderator <id> — добавить модератора\n"
        "• /add_developer <id> — добавить разработчика\n"
        "• /broadcast — опубликовать кнопку бронирования"
    )


@check_role("owner")
async def add_moderator_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /add_moderator <user_id> — owner adds a moderator."""
    user_id = update.effective_user.id
    db_session: AsyncSession = context.bot_data["db_session"]

    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /add_moderator <user_id>\n"
            "Пример: /add_moderator 123456789"
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id. Укажите число.")
        return

    # Check if target is already an admin
    if await user_has_role(db_session, target_user_id, ["owner", "moderator", "developer"]):
        await update.message.reply_text(
            f"ℹ️ Пользователь {target_user_id} уже является администратором."
        )
        return

    admin = Admin(
        user_id=target_user_id,
        role="moderator",
        added_by=(
            await db_session.execute(
                select(Admin).where(Admin.user_id == user_id)
            )
        ).scalar_one_or_none().id if user_id else None,
    )
    db_session.add(admin)
    await db_session.commit()

    await _log_action(
        db_session, "moderator_added",
        user_id=user_id,
        details={"target_user_id": target_user_id},
    )

    await update.message.reply_text(
        f"✅ Пользователь {target_user_id} назначен модератором."
    )


@check_role("owner")
async def remove_moderator_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /remove_moderator <user_id> — owner removes a moderator."""
    user_id = update.effective_user.id
    db_session: AsyncSession = context.bot_data["db_session"]

    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /remove_moderator <user_id>"
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id.")
        return

    if target_user_id == user_id:
        await update.message.reply_text("❌ Вы не можете удалить самого себя.")
        return

    result = await db_session.execute(
        select(Admin).where(
            Admin.user_id == target_user_id, Admin.role == "moderator"
        )
    )
    admin = result.scalar_one_or_none()
    if not admin:
        await update.message.reply_text(
            f"ℹ️ Пользователь {target_user_id} не является модератором."
        )
        return

    await db_session.delete(admin)
    await db_session.commit()

    await _log_action(
        db_session, "moderator_removed",
        user_id=user_id,
        details={"target_user_id": target_user_id},
    )

    await update.message.reply_text(
        f"✅ Модератор {target_user_id} удалён."
    )


@check_admin
async def moderators_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /moderators — list all moderators."""
    db_session: AsyncSession = context.bot_data["db_session"]

    result = await db_session.execute(
        select(Admin).where(Admin.role == "moderator")
    )
    moderators = result.scalars().all()

    if not moderators:
        await update.message.reply_text(
            "📋 Нет назначенных модераторов."
        )
        return

    lines = ["📋 <b>Модераторы канала:</b>"]
    for m in moderators:
        lines.append(f"• {m.user_id} (@{m.username or 'no_username'})")
    lines.append(f"\nВсего: {len(moderators)}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


@check_role("owner")
async def add_developer_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /add_developer <user_id> — owner adds a developer."""
    user_id = update.effective_user.id
    db_session: AsyncSession = context.bot_data["db_session"]

    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /add_developer <user_id>"
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id.")
        return

    if await user_has_role(db_session, target_user_id, ["owner", "moderator", "developer"]):
        await update.message.reply_text(
            f"ℹ️ Пользователь {target_user_id} уже является администратором."
        )
        return

    admin = Admin(user_id=target_user_id, role="developer")
    db_session.add(admin)
    await db_session.commit()

    await _log_action(
        db_session, "developer_added",
        user_id=user_id,
        details={"target_user_id": target_user_id},
    )

    await update.message.reply_text(
        f"✅ Пользователь {target_user_id} назначен разработчиком."
    )


@check_role("owner")
async def remove_developer_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /remove_developer <user_id> — owner removes a developer."""
    user_id = update.effective_user.id
    db_session: AsyncSession = context.bot_data["db_session"]

    if not context.args:
        await update.message.reply_text(
            "ℹ️ Использование: /remove_developer <user_id>"
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Неверный формат user_id.")
        return

    result = await db_session.execute(
        select(Admin).where(
            Admin.user_id == target_user_id, Admin.role == "developer"
        )
    )
    admin = result.scalar_one_or_none()
    if not admin:
        await update.message.reply_text(
            f"ℹ️ Пользователь {target_user_id} не является разработчиком."
        )
        return

    await db_session.delete(admin)
    await db_session.commit()

    await _log_action(
        db_session, "developer_removed",
        user_id=user_id,
        details={"target_user_id": target_user_id},
    )

    await update.message.reply_text(
        f"✅ Разработчик {target_user_id} удалён."
    )


@check_admin
async def developers_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Handle /developers — list all developers."""
    db_session: AsyncSession = context.bot_data["db_session"]

    result = await db_session.execute(
        select(Admin).where(Admin.role == "developer")
    )
    developers = result.scalars().all()

    if not developers:
        await update.message.reply_text("📋 Нет назначенных разработчиков.")
        return

    lines = ["📋 <b>Разработчики:</b>"]
    for d in developers:
        lines.append(f"• {d.user_id} (@{d.username or 'no_username'})")
    lines.append(f"\nВсего: {len(developers)}")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")
