from __future__ import annotations

import logging
import os
import shutil
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import psutil
from fastapi import APIRouter, Request
from sqlalchemy import text

from tbot_sheduler.core.config import BOT_VERSION, DB_PATH

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


class HealthStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    DOWN = "down"


EMOJI_MAP = {
    HealthStatus.OK: "✅",
    HealthStatus.DEGRADED: "⚠️",
    HealthStatus.DOWN: "❌",
}


@dataclass
class HealthContext:
    """Container for health check dependencies.

    Can be populated from either FastAPI request or bot application.
    """

    engine: Any = None
    bot_app: Any = None
    session_maker: Any = None
    started_at: float = field(default_factory=time.monotonic)


def _extract_context(request_or_bot: Request | Any) -> HealthContext:
    """Create HealthContext from FastAPI Request or bot Application."""
    ctx = HealthContext()

    if isinstance(request_or_bot, Request):
        ctx.engine = getattr(request_or_bot.app.state, "engine", None)
        ctx.bot_app = getattr(request_or_bot.app.state, "bot_app", None)
        ctx.session_maker = getattr(request_or_bot.app.state, "session_maker", None)
        ctx.started_at = getattr(
            request_or_bot.app.state, "started_at", time.monotonic()
        )
    else:
        # Bot Application
        ctx.bot_app = request_or_bot
        ctx.engine = getattr(request_or_bot, "_health_engine", None)
        ctx.session_maker = getattr(request_or_bot, "_health_session_maker", None)
        ctx.started_at = getattr(
            request_or_bot, "_start_time", time.monotonic()
        )

    return ctx


async def _check_database(ctx: HealthContext) -> dict:
    """Check database connectivity and WAL mode."""
    try:
        if ctx.engine is None:
            return {"status": HealthStatus.DOWN, "detail": "engine not initialized"}

        async with ctx.engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            row = await conn.execute(text("PRAGMA journal_mode"))
            mode = row.scalar()

            size = DB_PATH.stat().st_size if DB_PATH.exists() else 0

            status = HealthStatus.OK
            if mode != "wal":
                detail = f"journal_mode={mode} (expected wal)"
                status = HealthStatus.DEGRADED
            else:
                detail = f"wal_mode=ON, size_mb={size / 1_000_000:.1f}"

    except Exception as e:
        return {"status": HealthStatus.DOWN, "detail": str(e)}

    return {"status": status, "detail": detail}


async def _check_bot(ctx: HealthContext) -> dict:
    """Check if bot application is running."""
    application = ctx.bot_app
    if application is None or not application.running:
        return {"status": HealthStatus.DOWN, "detail": "bot is not running"}

    jq = application.job_queue
    queue_size = len(jq.jobs()) if jq else 0

    status = HealthStatus.OK
    detail = f"running, job_queue_size={queue_size}"

    if queue_size > 1000:
        status = HealthStatus.DEGRADED
        detail += " (queue > 1000)"

    return {"status": status, "detail": detail}


async def _check_telegram_api(ctx: HealthContext) -> dict:
    """Check Telegram API connectivity."""
    application = ctx.bot_app
    if application is None:
        return {"status": HealthStatus.DOWN, "detail": "bot not initialized"}

    start = time.monotonic()
    try:
        me = await application.bot.get_me()
        latency = (time.monotonic() - start) * 1000

        status = HealthStatus.OK
        detail = f"latency_ms={int(latency)}, bot_name={me.username}"

        if latency > 2000:
            status = HealthStatus.DEGRADED
            detail += " (high latency)"
    except Exception as e:
        return {"status": HealthStatus.DOWN, "detail": str(e)}

    return {"status": status, "detail": detail}


async def _check_disk() -> dict:
    """Check disk space."""
    try:
        st = shutil.disk_usage("/")
        free_mb = st.free / 1_000_000
        total_mb = st.total / 1_000_000

        status = HealthStatus.OK
        detail = f"free_mb={int(free_mb)}, total_mb={int(total_mb)}"

        if free_mb < 1000:
            status = HealthStatus.DEGRADED
            detail += " (disk space < 1GB)"
    except Exception as e:
        return {"status": HealthStatus.DOWN, "detail": str(e)}

    return {"status": status, "detail": detail}


async def _check_memory() -> dict:
    """Check memory usage."""
    try:
        process = psutil.Process()
        rss_mb = process.memory_info().rss / 1_000_000
        available = psutil.virtual_memory().available / 1_000_000

        status = HealthStatus.OK
        detail = f"rss_mb={int(rss_mb)}, available_mb={int(available)}"

        if available < 200:
            status = HealthStatus.DEGRADED
            detail += " (low memory)"
    except Exception as e:
        return {"status": HealthStatus.DOWN, "detail": str(e)}

    return {"status": status, "detail": detail}


async def _check_scheduler(ctx: HealthContext) -> dict:
    """Check heartbeat: pending notifications."""
    try:
        maker = ctx.session_maker
        if maker is None:
            return {"status": HealthStatus.DOWN, "detail": "no session_maker available"}

        async with maker() as session:
            result = await session.execute(
                text(
                    "SELECT COUNT(*) FROM notification "
                    "WHERE sent = 0 AND notify_at <= datetime('now')"
                )
            )
            count = result.scalar() or 0

        status = HealthStatus.OK if count == 0 else HealthStatus.DEGRADED
        detail = f"pending_notifications={count}"
    except Exception as e:
        return {"status": HealthStatus.DOWN, "detail": str(e)}

    return {"status": status, "detail": detail}


async def run_healthcheck(request_or_bot: Request | Any) -> dict:
    """Run all health checks and return aggregated result.

    Args:
        request_or_bot: FastAPI Request object or telegram.ext.Application

    Returns:
        Dict with overall status, version, uptime and per-check results.
    """
    import asyncio

    ctx = _extract_context(request_or_bot)
    start = time.monotonic()

    checks = await asyncio.gather(
        _check_database(ctx),
        _check_bot(ctx),
        _check_telegram_api(ctx),
        _check_disk(),
        _check_memory(),
        _check_scheduler(ctx),
        return_exceptions=True,
    )

    results = {}
    check_names = [
        "database", "bot", "telegram_api",
        "disk", "memory", "scheduler",
    ]

    for name, check in zip(check_names, checks):
        if isinstance(check, Exception):
            results[name] = {
                "status": HealthStatus.DOWN,
                "detail": str(check),
            }
        else:
            results[name] = check

    # Overall status
    has_down = any(
        c.get("status") == HealthStatus.DOWN for c in results.values()
    )
    has_degraded = any(
        c.get("status") == HealthStatus.DEGRADED for c in results.values()
    )

    if has_down:
        overall = HealthStatus.DOWN
    elif has_degraded:
        overall = HealthStatus.DEGRADED
    else:
        overall = HealthStatus.OK

    return {
        "status": overall,
        "version": BOT_VERSION,
        "uptime_seconds": int(
            time.monotonic() - ctx.started_at
        ),
        "response_time_ms": int((time.monotonic() - start) * 1000),
        "checks": results,
    }


@router.get("/health")
async def health_endpoint(request: Request) -> dict:
    """Health check endpoint."""
    return await run_healthcheck(request)
