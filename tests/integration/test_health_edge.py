"""Extended integration tests for health endpoint edge cases."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from tbot_sheduler.api.router import api_router


class TestHealthEdgeCases:
    """Test health endpoint edge cases."""

    @pytest.fixture
    def app_with_bot(self, db_engine):
        """Create app with a working mock bot."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

        app = FastAPI()
        app.include_router(api_router)
        app.state.engine = db_engine

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        app.state.session_maker = maker

        import time
        app.state.started_at = time.monotonic()

        # Mock bot that's running
        mock_bot = MagicMock()
        mock_bot.get_me = AsyncMock(return_value=MagicMock(username="test_bot"))
        mock_application = MagicMock()
        mock_application.running = True
        mock_application.bot = mock_bot
        mock_application.job_queue = MagicMock()
        mock_application.job_queue.jobs = MagicMock(return_value=[])
        app.state.bot_app = mock_application

        return app

    @pytest.fixture
    def app_without_bot(self, db_engine):
        """Create app without a running bot."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

        app = FastAPI()
        app.include_router(api_router)
        app.state.engine = db_engine

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        app.state.session_maker = maker

        import time
        app.state.started_at = time.monotonic()

        # Bot exists but not running
        mock_application = MagicMock()
        mock_application.running = False
        app.state.bot_app = mock_application

        return app

    @pytest.fixture
    def app_no_bot(self, db_engine):
        """Create app with no bot at all."""
        from sqlalchemy.ext.asyncio import async_sessionmaker, AsyncSession

        app = FastAPI()
        app.include_router(api_router)
        app.state.engine = db_engine

        maker = async_sessionmaker(
            db_engine, class_=AsyncSession, expire_on_commit=False
        )
        app.state.session_maker = maker

        import time
        app.state.started_at = time.monotonic()

        # No bot_app set
        return app

    async def test_health_with_bot_running(self, app_with_bot):
        """Test health with a running bot."""
        async with AsyncClient(
            transport=ASGITransport(app=app_with_bot),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")
            data = response.json()
            assert "bot" in data["checks"]
            assert "telegram_api" in data["checks"]
            assert response.status_code == 200

    async def test_health_without_bot_running(self, app_without_bot):
        """Test health with a bot that is not running."""
        async with AsyncClient(
            transport=ASGITransport(app=app_without_bot),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")
            data = response.json()
            bot_check = data["checks"]["bot"]
            assert bot_check["status"] == "down"

    async def test_health_with_no_bot(self, app_no_bot):
        """Test health with no bot configured."""
        async with AsyncClient(
            transport=ASGITransport(app=app_no_bot),
            base_url="http://test",
        ) as client:
            response = await client.get("/health")
            data = response.json()
            bot_check = data["checks"]["bot"]
            assert bot_check["status"] == "down"
