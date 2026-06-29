"""Unit tests for auth/role checking."""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Admin


class TestUserHasRole:
    """Test user_has_role function."""

    async def test_owner_has_owner_role(self, db_session: AsyncSession):
        """Test owner user has 'owner' role."""
        from tbot_sheduler.core.auth import user_has_role

        admin = Admin(user_id=1001, username="owner1", role="owner")
        db_session.add(admin)
        await db_session.commit()

        assert await user_has_role(db_session, 1001, "owner") is True

    async def test_owner_has_any_role(self, db_session: AsyncSession):
        """Test owner passes check for any role."""
        from tbot_sheduler.core.auth import user_has_role

        admin = Admin(user_id=1002, username="owner2", role="owner")
        db_session.add(admin)
        await db_session.commit()

        assert await user_has_role(db_session, 1002, ["owner", "moderator"]) is True

    async def test_moderator_does_not_have_owner(self, db_session: AsyncSession):
        """Test moderator does not have owner role."""
        from tbot_sheduler.core.auth import user_has_role

        admin = Admin(user_id=1003, username="mod1", role="moderator")
        db_session.add(admin)
        await db_session.commit()

        assert await user_has_role(db_session, 1003, "owner") is False

    async def test_developer_has_developer_role(self, db_session: AsyncSession):
        """Test developer has 'developer' role."""
        from tbot_sheduler.core.auth import user_has_role

        admin = Admin(user_id=1004, username="dev1", role="developer")
        db_session.add(admin)
        await db_session.commit()

        assert await user_has_role(db_session, 1004, "developer") is True

    async def test_developer_cannot_access_slot_commands(
        self, db_session: AsyncSession
    ):
        """Test developer does not have owner or moderator role."""
        from tbot_sheduler.core.auth import user_has_role

        admin = Admin(user_id=1005, username="dev2", role="developer")
        db_session.add(admin)
        await db_session.commit()

        assert await user_has_role(db_session, 1005, ["owner", "moderator"]) is False

    async def test_unknown_user_has_no_role(self, db_session: AsyncSession):
        """Test a user not in admin table has no roles."""
        from tbot_sheduler.core.auth import user_has_role

        assert await user_has_role(db_session, 999999, "owner") is False
        assert await user_has_role(db_session, 999999, ["owner", "moderator"]) is False

    async def test_role_cache_hit(self, db_session: AsyncSession):
        """Test role cache returns cached value without DB query."""
        from tbot_sheduler.core.auth import user_has_role, _role_cache

        admin = Admin(user_id=2001, username="cached", role="owner")
        db_session.add(admin)
        await db_session.commit()

        # First call - should query DB
        result1 = await user_has_role(db_session, 2001, "owner")
        assert result1 is True
        assert 2001 in _role_cache

        # Second call - should use cache
        result2 = await user_has_role(db_session, 2001, "owner")
        assert result2 is True

    async def test_role_cache_expires(self, db_session: AsyncSession):
        """Test role cache expires after 5 minutes."""
        from tbot_sheduler.core.auth import user_has_role, _role_cache, CACHE_TTL

        admin = Admin(user_id=3001, username="expire", role="moderator")
        db_session.add(admin)
        await db_session.commit()

        # Populate cache
        await user_has_role(db_session, 3001, "moderator")
        assert 3001 in _role_cache

        # Simulate cache expiry
        original_ttl = CACHE_TTL
        _role_cache[3001] = (_role_cache[3001][0], time.monotonic() - 301)

        # Should re-query
        result = await user_has_role(db_session, 3001, "moderator")
        assert result is True
        assert _role_cache[3001][1] > time.monotonic() - 10


class TestCheckAdminDecorator:
    """Test @check_admin decorator."""

    @pytest.fixture
    def mock_update(self):
        """Create a mock Update with user."""
        from telegram import User, Message, Chat
        update = MagicMock()
        user = MagicMock(spec=User)
        user.id = 5001
        update.effective_user = user

        chat = MagicMock(spec=Chat)
        chat.id = 5001
        chat.type = "private"
        update.effective_chat = chat

        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock CallbackContext with db_session."""
        context = MagicMock()
        context.bot_data = {}
        return context

    async def test_admin_decorator_allows_admin(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_admin allows admins through."""
        from tbot_sheduler.core.auth import check_admin

        admin = Admin(user_id=5001, username="admin", role="owner")
        db_session.add(admin)
        await db_session.commit()

        mock_update.effective_user.id = 5001

        # Create a mock handler function
        mock_handler = AsyncMock()
        wrapped = check_admin(mock_handler)

        # Need context.bot_data with db_session
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_awaited_once()

    async def test_admin_decorator_blocks_non_admin(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_admin blocks non-admins."""
        from tbot_sheduler.core.auth import check_admin

        mock_update.effective_user.id = 99999
        mock_handler = AsyncMock()
        wrapped = check_admin(mock_handler)
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_not_awaited()
        mock_update.message.reply_text.assert_awaited_once()


class TestCheckRoleDecorator:
    """Test @check_role decorator."""

    @pytest.fixture
    def mock_update(self):
        """Create a mock Update with user."""
        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 6001
        update.effective_chat = MagicMock()
        update.effective_chat.type = "private"
        message = MagicMock()
        message.reply_text = AsyncMock()
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_context(self):
        """Create a mock CallbackContext."""
        context = MagicMock()
        context.bot_data = {}
        return context

    async def test_check_role_owner_allows_owner(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_role('owner') allows owner."""
        from tbot_sheduler.core.auth import check_role

        admin = Admin(user_id=6001, role="owner")
        db_session.add(admin)
        await db_session.commit()

        mock_handler = AsyncMock()
        wrapped = check_role("owner")(mock_handler)
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_awaited_once()

    async def test_check_role_blocks_moderator(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_role('owner') blocks moderator."""
        from tbot_sheduler.core.auth import check_role

        mock_update.effective_user.id = 6002
        admin = Admin(user_id=6002, role="moderator")
        db_session.add(admin)
        await db_session.commit()

        mock_handler = AsyncMock()
        wrapped = check_role("owner")(mock_handler)
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_not_awaited()

    async def test_check_role_multiple_allowed(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_role('owner', 'moderator') allows both."""
        from tbot_sheduler.core.auth import check_role

        admin = Admin(user_id=6003, role="moderator")
        db_session.add(admin)
        await db_session.commit()

        mock_handler = AsyncMock()
        wrapped = check_role("owner", "moderator")(mock_handler)
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_awaited_once()

    async def test_check_role_blocks_developer_from_slots(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_role('owner', 'moderator') blocks developer."""
        from tbot_sheduler.core.auth import check_role

        mock_update.effective_user.id = 6004
        admin = Admin(user_id=6004, role="developer")
        db_session.add(admin)
        await db_session.commit()

        mock_handler = AsyncMock()
        wrapped = check_role("owner", "moderator")(mock_handler)
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_not_awaited()

    async def test_check_role_allows_developer_health(
        self, mock_update, mock_context, db_session
    ):
        """Test @check_role('developer', 'owner') allows developer."""
        from tbot_sheduler.core.auth import check_role

        admin = Admin(user_id=6005, role="developer")
        db_session.add(admin)
        await db_session.commit()

        mock_handler = AsyncMock()
        wrapped = check_role("developer", "owner")(mock_handler)
        mock_context.bot_data["db"] = db_session

        await wrapped(mock_update, mock_context)
        mock_handler.assert_awaited_once()


class TestAuthDecoratorNoneChecks:
    """Test that auth decorators handle None effective_user/message safely."""

    @pytest.fixture
    def mock_context(self):
        context = MagicMock()
        context.bot_data = {}
        return context

    async def test_admin_decorator_none_user(
        self, mock_context
    ):
        """Test @check_admin with None effective_user doesn't crash."""
        from tbot_sheduler.core.auth import check_admin

        update = MagicMock()
        update.effective_user = None

        mock_handler = AsyncMock()
        wrapped = check_admin(mock_handler)

        await wrapped(update, mock_context)
        # Handler should NOT be called
        mock_handler.assert_not_awaited()

    async def test_admin_decorator_none_message(
        self, mock_context, db_session
    ):
        """Test @check_admin with None message but effective_chat doesn't crash."""
        from tbot_sheduler.core.auth import check_admin

        from telegram import Chat
        effective_chat = MagicMock(spec=Chat)
        effective_chat.id = -1001234567
        effective_chat.send_message = AsyncMock()

        update = MagicMock()
        update.effective_user = MagicMock()
        update.effective_user.id = 7001
        update.effective_chat = effective_chat
        update.message = None  # e.g. callback query

        mock_context.bot_data["db"] = db_session

        mock_handler = AsyncMock()
        wrapped = check_admin(mock_handler)

        await wrapped(update, mock_context)
        # Handler should NOT be called (user is not admin)
        mock_handler.assert_not_awaited()
        # Error message should go through effective_chat
        effective_chat.send_message.assert_awaited_once()

    async def test_check_role_none_user(
        self, mock_context
    ):
        """Test @check_role with None effective_user doesn't crash."""
        from tbot_sheduler.core.auth import check_role

        update = MagicMock()
        update.effective_user = None

        mock_handler = AsyncMock()
        wrapped = check_role("owner")(mock_handler)

        await wrapped(update, mock_context)
        # Handler should NOT be called
        mock_handler.assert_not_awaited()
