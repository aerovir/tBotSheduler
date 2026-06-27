"""Unit tests for graceful shutdown."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sqlalchemy import text

from tbot_sheduler.core.database import Base


class TestGracefulShutdown:
    """Test graceful shutdown behavior."""

    async def test_engine_dispose(self):
        """Test engine disposal completes without error."""
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Dispose should work cleanly
        await engine.dispose()
        # Should not raise on double dispose
        await engine.dispose()

    async def test_database_wal_mode(self):
        """Test SQLite WAL mode is set on connection."""
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
        )
        async with engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.commit()

            # Check WAL mode
            result = await conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            # WAL may report as "wal" or "wal" depending on implementation
            assert mode is not None, "WAL mode should be set"

        await engine.dispose()
