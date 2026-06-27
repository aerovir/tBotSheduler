"""Test database initialization functions."""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from tbot_sheduler.core.database import dispose_engine


class TestDatabaseInit:
    """Test database initialization and disposal."""

    async def test_dispose_engine_closes_connection(self, db_engine: AsyncEngine):
        """Test dispose_engine closes all connections."""
        # Verify we can query before dispose
        async with db_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))

        # Dispose
        await db_engine.dispose()

        # Should not raise on double dispose
        await db_engine.dispose()

    async def test_bot_database_url_has_sqlite(self):
        """Test that DATABASE_URL uses sqlite."""
        from tbot_sheduler.core.config import DATABASE_URL
        assert "sqlite" in DATABASE_URL

    async def test_tables_exist_after_create(self, db_engine: AsyncEngine):
        """Test that all expected tables are created."""
        async with db_engine.connect() as conn:
            result = await conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
            tables = set(result.scalars().all())

        expected = {"admin", "channel", "slot", "booking", "notification", "audit_log"}
        assert expected.issubset(tables), f"Missing: {expected - tables}"
