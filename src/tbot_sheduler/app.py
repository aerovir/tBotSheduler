from __future__ import annotations

import asyncio
import logging
import signal
import time
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    Defaults,
    DefaultRateLimiter,
    PicklePersistence,
)
from telegram.constants import ParseMode

from tbot_sheduler.api.router import api_router
from tbot_sheduler.bot.handlers import start_command
from tbot_sheduler.bot.admin_handlers import (
    setup_command,
    add_moderator_command,
    remove_moderator_command,
    moderators_command,
    add_developer_command,
    remove_developer_command,
    developers_command,
)
from tbot_sheduler.bot.developer_handlers import (
    health_command,
    logs_command,
    version_command,
)
from tbot_sheduler.bot.slot_handlers import (
    create_slots_command,
    slots_command,
    free_slot_command,
    broadcast_command,
)
from tbot_sheduler.bot.scheduler import check_pending
from tbot_sheduler.core.config import BOT_TOKEN, LOG_LEVEL
from tbot_sheduler.core.database import (
    Base,
    create_tables,
    dispose_engine,
    get_engine,
    get_session_maker,
)
from tbot_sheduler.core.logging import setup_logging

logger = logging.getLogger(__name__)

# Global flag for graceful shutdown
_shutdown_event = asyncio.Event()


def _signal_handler(sig: int, frame) -> None:
    """Handle shutdown signals."""
    logger.info("Received signal %s, initiating graceful shutdown", sig)
    _shutdown_event.set()


async def _check_pending_on_startup(
    db_session: AsyncSession, bot
) -> None:
    """Check for pending notifications on startup and send them."""
    try:
        count = await check_pending(db_session, bot)
        if count > 0:
            logger.info(
                "Startup heartbeat: sent %d pending notifications",
                count,
            )
        else:
            logger.info("Startup heartbeat: no pending notifications")
    except Exception as e:
        logger.error("Startup heartbeat check failed: %s", e)


async def _on_error(update: Update, context) -> None:
    """Global error handler for the bot."""
    logger.error(
        "Unhandled error: %s | Update: %s", context.error, update
    )


def _create_bot_app() -> Application:
    """Create and configure the Telegram bot Application."""
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set")

    # DefaultRateLimiter — 30 messages per second (Telegram limit for groups)
    rate_limiter = DefaultRateLimiter(
        overall_max_rate=30,
        overall_time_period=1.0,
        group_max_rate=20,
        group_time_period=1.0,
    )

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .rate_limiter(rate_limiter)
        .defaults(Defaults(parse_mode=ParseMode.HTML))
        .build()
    )

    # Register handlers
    # Public
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("setup", setup_command))

    # Owner-only delegation commands
    application.add_handler(CommandHandler("add_moderator", add_moderator_command))
    application.add_handler(CommandHandler("remove_moderator", remove_moderator_command))
    application.add_handler(CommandHandler("moderators", moderators_command))
    application.add_handler(CommandHandler("add_developer", add_developer_command))
    application.add_handler(CommandHandler("remove_developer", remove_developer_command))
    application.add_handler(CommandHandler("developers", developers_command))

    # Developer + owner technical commands
    application.add_handler(CommandHandler("health", health_command))
    application.add_handler(CommandHandler("logs", logs_command))
    application.add_handler(CommandHandler("version", version_command))

    # Owner + moderator slot management
    application.add_handler(CommandHandler("create_slots", create_slots_command))
    application.add_handler(CommandHandler("slots", slots_command))
    application.add_handler(CommandHandler("free_slot", free_slot_command))
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    # Global error handler
    application.add_error_handler(_on_error)

    return application


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: startup and shutdown."""
    # Setup logging
    setup_logging()
    logger.info(
        "Starting tBotSheduler v%s with log level %s...",
        "0.1.0",
        LOG_LEVEL,
    )

    # Register signal handlers
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(
                sig,
                lambda s=sig: _signal_handler(s, None),
            )
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            signal.signal(sig, _signal_handler)

    # Startup
    started_at = time.monotonic()
    app.state.started_at = started_at

    # Database
    engine = await get_engine()
    app.state.engine = engine
    await create_tables()

    session_maker = await get_session_maker()
    app.state.session_maker = session_maker

    # Bot
    bot_app = _create_bot_app()
    app.state.bot_app = bot_app

    # Run startup checks with a short-lived session
    async with session_maker() as startup_session:
        await _check_pending_on_startup(startup_session, bot_app.bot)

    # Healthcheck on startup
    from tbot_sheduler.api.health import run_healthcheck

    # Create a mock request-like object for healthcheck
    from fastapi import Request as FastAPIRequest
    scope = {
        "type": "http",
        "app": app,
    }
    mock_request = FastAPIRequest(scope)  # type: ignore[arg-type]

    health_data = await run_healthcheck(mock_request)
    if health_data["status"] != "ok":
        logger.warning(
            "Healthcheck at startup: %s", health_data["status"]
        )
        for name, check in health_data["checks"].items():
            if check["status"] != "ok":
                logger.warning(
                    "  %s: %s — %s", name, check["status"], check["detail"]
                )
    else:
        logger.info("All health checks passed at startup")

    # Start the bot
    await bot_app.initialize()
    await bot_app.start()
    await bot_app.updater.start_polling()

    # Set bot_data — store session_maker, NOT a single session
    bot_app.bot_data["session_maker"] = session_maker
    bot_app.bot_data["engine"] = engine

    # Register recurring heartbeat: каждые 5 минут проверка просроченных уведомлений
    try:
        from tbot_sheduler.bot.notification_service import _heartbeat_callback
        bot_app.job_queue.run_repeating(
            _heartbeat_callback,
            interval=300,  # 5 минут
            first=60,      # первый запуск через 60 секунд после старта
        )
        logger.info("Heartbeat recurring job registered (every 300s)")
    except Exception as e:
        logger.warning("Could not register heartbeat job: %s", e)

    # Store engine + maker for bot healthcheck access
    bot_app._health_engine = engine
    bot_app._health_session_maker = session_maker
    bot_app._start_time = started_at

    logger.info("Bot started polling")

    yield  # App is running here

    # Shutdown
    logger.info("Shutting down...")
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

    await dispose_engine()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    """Create the FastAPI application."""
    app = FastAPI(
        title="tBotSheduler",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.include_router(api_router)

    return app
