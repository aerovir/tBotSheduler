"""Role checking and authorization for admin commands."""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from tbot_sheduler.models import Admin

logger = logging.getLogger(__name__)


async def _reply(update: Update, text: str) -> None:
    """Send a reply via message or chat, whichever is available."""
    if update.message:
        await update.message.reply_text(text)
    elif update.effective_chat:
        await update.effective_chat.send_message(text)

# Cache: {user_id: (role, timestamp)}
_role_cache: dict[int, tuple[str | None, float]] = {}
CACHE_TTL = 300  # 5 minutes


def invalidate_role_cache(user_id: int) -> None:
    """Remove a user's cached role so the next lookup hits the database.

    Call this when a user's role changes (added/removed as moderator, developer).
    """
    _role_cache.pop(user_id, None)
    logger.debug("Role cache invalidated for user %d", user_id)


async def user_has_role(
    db_session: AsyncSession,
    user_id: int,
    roles: str | list[str],
) -> bool:
    """Check if a user has one of the specified roles.

    Uses an in-memory cache with 5-minute TTL.

    Args:
        db_session: Database session
        user_id: Telegram user ID
        roles: Single role string or list of acceptable roles

    Returns:
        True if the user has one of the specified roles.
    """
    if isinstance(roles, str):
        roles = [roles]

    # Check cache first
    now = time.monotonic()
    if user_id in _role_cache:
        cached_role, cached_at = _role_cache[user_id]
        if now - cached_at < CACHE_TTL:
            return cached_role in roles if cached_role else False

    # Query database
    result = await db_session.execute(
        select(Admin).where(Admin.user_id == user_id)
    )
    admin = result.scalar_one_or_none()

    admin_role = admin.role if admin else None
    _role_cache[user_id] = (admin_role, now)

    return admin_role in roles if admin_role else False


def check_admin(
    handler: Callable[..., Any]
) -> Callable[..., Any]:
    """Decorator: allow only admins (any role: owner/moderator/developer).

    Usage:
        @check_admin
        async def my_handler(update, context): ...
    """

    @functools.wraps(handler)
    async def wrapper(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        # Безопасная проверка: effective_user может быть None
        # (channel post, poll, callback от анонимного админа)
        if not update.effective_user:
            logger.warning("check_admin: no effective_user in update")
            return

        user_id = update.effective_user.id
        db_session: AsyncSession | None = context.bot_data.get("db")

        if db_session is None:
            logger.error("No db_session in context.bot_data")
            await _reply(update, "⚠️ Техническая ошибка. Попробуйте позже.")
            return

        if await user_has_role(db_session, user_id, ["owner", "moderator", "developer"]):
            return await handler(update, context, *args, **kwargs)

        logger.warning("Access denied for user %d (not an admin)", user_id)
        await _reply(update, "⛔ У вас нет прав для этой команды.")

    return wrapper


def check_role(*roles: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator: allow only users with one of the specified roles.

    Usage:
        @check_role('owner')
        async def owner_only_handler(update, context): ...

        @check_role('owner', 'moderator')
        async def moderator_or_owner_handler(update, context): ...

        @check_role('developer', 'owner')
        async def health_handler(update, context): ...
    """

    def decorator(
        handler: Callable[..., Any]
    ) -> Callable[..., Any]:
        @functools.wraps(handler)
        async def wrapper(
            update: Update,
            context: ContextTypes.DEFAULT_TYPE,
            *args: Any,
            **kwargs: Any,
        ) -> Any:
            # Безопасная проверка: effective_user может быть None
            if not update.effective_user:
                logger.warning("check_role: no effective_user in update")
                return

            user_id = update.effective_user.id
            db_session: AsyncSession | None = context.bot_data.get("db")

            if db_session is None:
                logger.error("No db_session in context.bot_data")
                await _reply(update, "⚠️ Техническая ошибка. Попробуйте позже.")
                return

            if await user_has_role(db_session, user_id, list(roles)):
                return await handler(update, context, *args, **kwargs)

            logger.warning(
                "Access denied for user %d (required roles: %s)",
                user_id,
                roles,
            )
            await _reply(update, "⛔ У вас нет прав для этой команды.")

        return wrapper

    return decorator
