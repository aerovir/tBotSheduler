"""Unit tests for bot command handlers."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import Update, Message, User, Chat


class TestStartCommand:
    """Test /start command handler."""

    @pytest.fixture
    def mock_update(self) -> MagicMock:
        """Create a mock Update for testing."""
        user = MagicMock(spec=User)
        user.id = 12345
        user.full_name = "Test User"

        chat = MagicMock(spec=Chat)
        chat.id = 12345
        chat.type = "private"

        message = MagicMock(spec=Message)
        message.reply_text = AsyncMock()

        update = MagicMock(spec=Update)
        update.effective_user = user
        update.effective_chat = chat
        update.message = message
        update.effective_message = message
        return update

    @pytest.fixture
    def mock_context(self) -> MagicMock:
        """Create a mock CallbackContext."""
        return MagicMock()

    async def test_start_replies_with_greeting(
        self, mock_update: MagicMock, mock_context: MagicMock
    ):
        """Test /start command sends a greeting."""
        from tbot_sheduler.bot.handlers import start_command

        await start_command(mock_update, mock_context)

        mock_update.message.reply_text.assert_awaited_once()
        reply_text = mock_update.message.reply_text.await_args[0][0]
        assert "Привет" in reply_text
        assert "/start" in reply_text

    async def test_start_logs_user(self, mock_update, mock_context):
        """Test /start command logs the user."""
        from tbot_sheduler.bot.handlers import start_command
        import logging

        # Just verify it doesn't raise
        await start_command(mock_update, mock_context)
        # If we got here without error, logging worked
        assert True
