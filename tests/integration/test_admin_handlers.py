"""Integration tests for admin command handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from tbot_sheduler.models import Admin, AuditLog, Channel


class TestSetupCommand:
    """Test /setup command."""

    @pytest.fixture
    def mock_update(self):
        """Create mock update for group chat."""
        update = MagicMock()
        update.effective_user.id = 10001
        update.effective_user.username = "test_admin"
        update.effective_user.full_name = "Test Admin"
        update.effective_chat.id = -100123456789
        update.effective_chat.type = "group"
        update.effective_chat.title = "Test Channel"
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_context(self, db_engine):
        """Create mock context with session_maker."""
        from sqlalchemy.ext.asyncio import AsyncSession
        maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        context = MagicMock()
        context.bot_data = {"session_maker": maker}
        return context

    async def test_setup_creates_owner(self, mock_update, mock_context, db_session):
        """Test /setup creates owner and channel."""
        from tbot_sheduler.bot.admin_handlers import setup_command
        from tbot_sheduler.core.auth import _role_cache
        _role_cache.clear()

        await setup_command(mock_update, mock_context)

        result = await db_session.execute(
            select(Admin).where(Admin.user_id == 10001)
        )
        admin = result.scalar_one()
        assert admin.role == "owner"
        assert admin.username == "test_admin"

        result = await db_session.execute(
            select(Channel).where(Channel.chat_id == -100123456789)
        )
        channel = result.scalar_one()
        assert channel.title == "Test Channel"
        assert channel.owner_id == admin.id

        log_result = await db_session.execute(
            select(AuditLog).where(AuditLog.action == "setup_completed")
        )
        log = log_result.scalar_one()
        assert log.user_id == 10001

    async def test_setup_in_private_chat(self, mock_update, mock_context):
        """Test /setup in private chat shows warning."""
        mock_update.effective_chat.type = "private"

        from tbot_sheduler.bot.admin_handlers import setup_command
        await setup_command(mock_update, mock_context)

        reply_text = mock_update.message.reply_text.call_args[0][0]
        assert "только в канале" in reply_text


class TestModerationDirect:
    """Test moderation functions directly (without decorators)."""

    @pytest.fixture
    def context(self, db_engine):
        from sqlalchemy.ext.asyncio import AsyncSession
        maker = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
        context = MagicMock()
        context.bot_data = {"session_maker": maker}
        return context

    @pytest.fixture
    def update(self):
        update = MagicMock()
        update.effective_user.id = 20001
        chat = MagicMock()
        chat.type = "private"
        update.effective_chat = chat
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    async def _setup_owner(self, db_session):
        from tbot_sheduler.core.auth import _role_cache
        _role_cache.clear()
        admin = Admin(user_id=20001, role="owner")
        db_session.add(admin)
        await db_session.commit()
        _role_cache.clear()

    async def test_add_moderator(self, update, context, db_session):
        """Test adding a moderator via handler."""
        from tbot_sheduler.bot.admin_handlers import add_moderator_command
        await self._setup_owner(db_session)

        context.args = ["30001"]
        update.effective_user.id = 20001
        await add_moderator_command(update, context)

        result = await db_session.execute(
            select(Admin).where(Admin.user_id == 30001)
        )
        admin = result.scalar_one()
        assert admin.role == "moderator"

    async def test_remove_moderator(self, update, context, db_session):
        """Test removing a moderator."""
        from tbot_sheduler.bot.admin_handlers import remove_moderator_command
        await self._setup_owner(db_session)

        admin = Admin(user_id=40001, role="moderator")
        db_session.add(admin)
        await db_session.commit()

        context.args = ["40001"]
        await remove_moderator_command(update, context)

        result = await db_session.execute(
            select(Admin).where(Admin.user_id == 40001)
        )
        assert result.scalar_one_or_none() is None

    async def test_add_developer(self, update, context, db_session):
        """Test adding a developer."""
        from tbot_sheduler.bot.admin_handlers import add_developer_command
        await self._setup_owner(db_session)

        context.args = ["50001"]
        await add_developer_command(update, context)

        result = await db_session.execute(
            select(Admin).where(Admin.user_id == 50001)
        )
        admin = result.scalar_one()
        assert admin.role == "developer"

    async def test_remove_developer(self, update, context, db_session):
        """Test removing a developer."""
        from tbot_sheduler.bot.admin_handlers import remove_developer_command
        await self._setup_owner(db_session)

        admin = Admin(user_id=60001, role="developer")
        db_session.add(admin)
        await db_session.commit()

        context.args = ["60001"]
        await remove_developer_command(update, context)

        result = await db_session.execute(
            select(Admin).where(Admin.user_id == 60001)
        )
        assert result.scalar_one_or_none() is None

    async def test_list_moderators(self, update, context, db_session):
        """Test listing moderators."""
        from tbot_sheduler.bot.admin_handlers import moderators_command
        await self._setup_owner(db_session)

        db_session.add(Admin(user_id=70001, role="moderator", username="mod1"))
        await db_session.commit()

        await moderators_command(update, context)
        reply_text = update.message.reply_text.call_args[0][0]
        assert "70001" in reply_text

    async def test_list_empty_moderators(self, update, context, db_session):
        """Test listing when no moderators exist."""
        from tbot_sheduler.bot.admin_handlers import moderators_command
        await self._setup_owner(db_session)

        await moderators_command(update, context)
        reply_text = update.message.reply_text.call_args[0][0]
        assert "Нет" in reply_text
