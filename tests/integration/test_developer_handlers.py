"""Integration tests for developer command handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select

from tbot_sheduler.models import Admin


@pytest_asyncio.fixture(autouse=True)
async def _setup_dev(db_session):
    """Create a developer admin for tests."""
    from tbot_sheduler.core.auth import _role_cache
    _role_cache.clear()
    admin = Admin(user_id=10001, role="developer")
    db_session.add(admin)
    await db_session.commit()
    _role_cache.clear()


class TestHealthCommand:
    """Test /health command."""

    @pytest.fixture
    def mock_update_pm(self):
        """Mock update from private chat."""
        update = MagicMock()
        update.effective_user.id = 10001
        chat = MagicMock()
        chat.type = "private"
        update.effective_chat = chat
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_update_group(self):
        """Mock update from group chat."""
        update = MagicMock()
        update.effective_user.id = 10001
        chat = MagicMock()
        chat.type = "group"
        update.effective_chat = chat
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_context(self, db_engine):
        """Mock context with bot app."""
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        context = MagicMock()
        context.bot_data = {"session_maker": maker}
        mock_bot = MagicMock()
        mock_bot.send_message = AsyncMock()
        mock_app = MagicMock()
        mock_app.bot = mock_bot
        mock_app._health_engine = None
        mock_app._health_session_maker = None
        mock_app._start_time = 1000000.0
        mock_app.running = True
        mock_app.job_queue = MagicMock()
        mock_app.job_queue.jobs = MagicMock(return_value=[])
        context.application = mock_app
        context.bot = mock_bot
        return context

    @patch("tbot_sheduler.bot.developer_handlers.run_healthcheck")
    async def test_health_in_private(
        self, mock_run_healthcheck, mock_update_pm, mock_context
    ):
        """Test /health in private chat."""
        from tbot_sheduler.bot.developer_handlers import health_command

        mock_run_healthcheck.return_value = {
            "status": "ok",
            "version": "0.1.0",
            "uptime_seconds": 3600,
            "response_time_ms": 45,
            "checks": {
                "database": {"status": "ok", "detail": "wal_mode=ON"},
                "bot": {"status": "ok", "detail": "running"},
            },
        }

        await health_command(mock_update_pm, mock_context)

        mock_update_pm.message.reply_text.assert_awaited_once()
        reply_text = mock_update_pm.message.reply_text.call_args[0][0]
        assert "✅" in reply_text

    @patch("tbot_sheduler.bot.developer_handlers.run_healthcheck")
    async def test_health_in_group_sends_pm(
        self, mock_run_healthcheck, mock_update_group, mock_context
    ):
        """Test /health in group chat sends result to PM."""
        from tbot_sheduler.bot.developer_handlers import health_command

        mock_run_healthcheck.return_value = {
            "status": "ok",
            "version": "0.1.0",
            "uptime_seconds": 100,
            "response_time_ms": 50,
            "checks": {},
        }

        await health_command(mock_update_group, mock_context)

        mock_update_group.message.reply_text.assert_awaited_once()
        reply_text = mock_update_group.message.reply_text.call_args[0][0]
        assert "личные сообщения" in reply_text
        mock_context.application.bot.send_message.assert_awaited_once()


class TestVersionCommand:
    """Test /version command."""

    @pytest.fixture
    def mock_update(self):
        update = MagicMock()
        update.effective_user.id = 10001
        chat = MagicMock()
        chat.type = "private"
        update.effective_chat = chat
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_context(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
        maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        context = MagicMock()
        context.bot_data = {"session_maker": maker}
        mock_app = MagicMock()
        mock_app._start_time = 1000000.0
        context.application = mock_app
        return context

    async def test_version_shows_info(self, mock_update, mock_context):
        """Test /version shows version and uptime."""
        from tbot_sheduler.bot.developer_handlers import version_command

        await version_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_awaited_once()
        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "0.1.0" in reply_text
