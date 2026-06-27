"""Unit tests for configuration module."""
from __future__ import annotations

import os

import pytest


class TestConfig:
    """Test environment configuration."""

    def test_version_is_set(self):
        """Test that BOT_VERSION is defined."""
        from tbot_sheduler.core.config import BOT_VERSION
        assert BOT_VERSION == "0.1.0"

    def test_bot_token_has_test_value(self):
        """Test that BOT_TOKEN is set from env."""
        from tbot_sheduler.core.config import BOT_TOKEN
        assert BOT_TOKEN == "test:fake_token_12345"

    def test_log_level_default(self):
        """Test LOG_LEVEL has a sensible default."""
        from tbot_sheduler.core.config import LOG_LEVEL
        assert LOG_LEVEL in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_db_path_is_pathlike(self):
        """Test that DB_PATH is a Path object."""
        from tbot_sheduler.core.config import DB_PATH
        assert hasattr(DB_PATH, "resolve")  # Path has resolve method
