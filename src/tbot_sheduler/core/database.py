from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from tbot_sheduler.core.config import DATABASE_URL

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_async_session_maker: async_sessionmaker[AsyncSession] | None = None


async def get_engine() -> AsyncEngine:
    """Get or create the database engine with WAL mode and busy timeout."""
    global _engine
    if _engine is None:
        logger.info("Creating database engine: %s", DATABASE_URL)
        _engine = create_async_engine(
            DATABASE_URL,
            echo=False,
            connect_args={
                "check_same_thread": False,
            },
        )

        # Configure WAL mode and busy timeout on first connection
        async with _engine.connect() as conn:
            await conn.exec_driver_sql("PRAGMA journal_mode=WAL")
            await conn.exec_driver_sql("PRAGMA busy_timeout=5000")
            await conn.exec_driver_sql("PRAGMA foreign_keys=ON")
            await conn.commit()

    return _engine


async def get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Get or create the async session maker."""
    global _async_session_maker
    if _async_session_maker is None:
        engine = await get_engine()
        _async_session_maker = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_maker


async def create_tables() -> None:
    """Create all tables defined in the Base metadata."""
    engine = await get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created successfully")


async def dispose_engine() -> None:
    """Dispose the database engine (for graceful shutdown)."""
    global _engine, _async_session_maker
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _async_session_maker = None
        logger.info("Database engine disposed")
