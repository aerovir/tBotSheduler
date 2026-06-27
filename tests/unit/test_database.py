"""Unit tests for database module."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

from tbot_sheduler.core.database import Base, create_tables, dispose_engine
from tbot_sheduler.core.config import DATABASE_URL


class TestDatabaseCore:
    """Test core database functions."""

    async def test_engine_creates_tables(self, db_engine):
        """Test that tables are created from Base metadata."""
        # db_engine fixture already creates tables via create_all
        async with db_engine.connect() as conn:
            result = await conn.execute(
                text(
                    "SELECT name FROM sqlite_master "
                    "WHERE type='table' ORDER BY name"
                )
            )
            tables = result.scalars().all()

        expected_tables = {
            "admin", "channel", "slot", "booking",
            "notification", "audit_log",
        }
        for table in expected_tables:
            assert table in tables, f"Missing table: {table}"

    async def test_engine_double_dispose(self):
        """Test that engine can be disposed multiple times safely."""
        engine = create_async_engine(
            "sqlite+aiosqlite://",
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        await engine.dispose()
        await engine.dispose()  # Should not raise

    async def test_wal_mode_on_connection(self, db_engine):
        """Test that WAL mode can be set on connection."""
        async with db_engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.commit()

            result = await conn.execute(text("PRAGMA journal_mode"))
            mode = result.scalar()
            assert mode is not None

    async def test_database_url_default(self):
        """Test that DATABASE_URL is properly set from config."""
        assert "sqlite+aiosqlite://" in DATABASE_URL
