"""Dependency injection: DB session per request/decorator."""
from __future__ import annotations

from functools import wraps
from typing import Any, AsyncGenerator, Callable

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes


async def get_db(request: Request) -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: create and yield a DB session per HTTP request.

    Usage:
        @router.post("/book")
        async def book_slot(body: BookingRequest, db: AsyncSession = Depends(get_db)):
            ...
    """
    maker = request.app.state.session_maker
    async with maker() as session:
        yield session


def with_db(
    handler: Callable[..., Any]
) -> Callable[..., Any]:
    """Decorator: open a DB session for a bot handler.

    The session is stored in ``context.bot_data["db"]`` and closed
    automatically when the handler returns.

    Must be the *outermost* decorator so the session is available to
    inner decorators such as ``@check_role`` / ``@check_admin``.

    Usage:
        @with_db
        @check_role("owner")
        async def my_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
            db = context.bot_data["db"]
            ...
    """

    @wraps(handler)
    async def wrapper(
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        maker = context.bot_data.get("session_maker")
        if maker is None:
            raise RuntimeError(
                "session_maker not found in context.bot_data. "
                "Ensure app.py stores it on startup."
            )
        async with maker() as session:
            context.bot_data["db"] = session
            try:
                return await handler(update, context, *args, **kwargs)
            finally:
                context.bot_data.pop("db", None)

    return wrapper
