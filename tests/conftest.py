"""Pytest fixtures for tBotSheduler tests."""
from __future__ import annotations

import os
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

# Set test env vars before importing app modules
os.environ["BOT_TOKEN"] = "test:fake_token_12345"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite://"

from tbot_sheduler.core.database import Base
from tbot_sheduler.models import Admin, Channel, Slot, Booking, Notification, AuditLog


@pytest_asyncio.fixture
async def db_engine() -> AsyncGenerator[AsyncEngine, None]:
    """Create an in-memory SQLite database for testing."""
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Create a session for testing."""
    maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine: AsyncEngine) -> AsyncGenerator[AsyncClient, None]:
    """Create an HTTP client with a FastAPI app that has a mock database."""
    from fastapi import FastAPI
    from tbot_sheduler.api.router import api_router
    from tbot_sheduler.core.database import get_session_maker

    app = FastAPI()
    app.include_router(api_router)

    # Set up app state
    app.state.engine = db_engine

    maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    app.state.session_maker = maker

    import time
    app.state.started_at = time.monotonic()

    # Mock bot app state
    from unittest.mock import AsyncMock, MagicMock
    mock_bot = MagicMock()
    mock_bot.get_me = AsyncMock(return_value=MagicMock(username="test_bot"))
    mock_application = MagicMock()
    mock_application.running = True
    mock_application.bot = mock_bot
    mock_application.job_queue = MagicMock()
    mock_application.job_queue.jobs = MagicMock(return_value=[])
    mock_application.bot_data = {"session_maker": maker}
    app.state.bot_app = mock_application

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac
