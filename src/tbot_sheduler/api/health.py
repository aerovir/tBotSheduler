from __future__ import annotations

import logging
import os
import shutil
import time
from enum import Enum

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


async def _check_database(request: Request) -> dict:
    """Check database connectivity and WAL mode."""
    try:
        engine = request.app.state.engine
        async with engine.connect() as conn:
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


async def _check_bot(request: Request) -> dict:
    """Check if bot application is running."""
    application = getattr(request.app.state, "bot_app", None)
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


async def _check_telegram_api(request: Request) -> dict:
    """Check Telegram API connectivity."""
    application = getattr(request.app.state, "bot_app", None)
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


async def _check_scheduler(request: Request) -> dict:
    """Check heartbeat: pending notifications."""
    try:
        db_session = getattr(request.app.state, "db_session", None)
        if db_session is None:
            return {"status": HealthStatus.DOWN, "detail": "db_session not initialized"}

        result = await db_session.execute(
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


async def run_healthcheck(request: Request) -> dict:
    """Run all health checks and return aggregated result."""
    import asyncio

    start = time.monotonic()

    checks = await asyncio.gather(
        _check_database(request),
        _check_bot(request),
        _check_telegram_api(request),
        _check_disk(),
        _check_memory(),
        _check_scheduler(request),
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
            time.monotonic() - getattr(request.app.state, "started_at", time.monotonic())
        ),
        "response_time_ms": int((time.monotonic() - start) * 1000),
        "checks": results,
    }


@router.get("/health")
async def health_endpoint(request: Request) -> dict:
    """Health check endpoint."""
    return await run_healthcheck(request)
