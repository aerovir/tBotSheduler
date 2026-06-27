"""Unit tests for logging configuration."""
from __future__ import annotations

import logging
import os

import pytest


class TestLogging:
    """Test logging setup."""

    @pytest.fixture(autouse=True)
    def cleanup_loggers(self):
        """Remove our handlers after each test."""
        yield
        root = logging.getLogger()
        for handler in list(root.handlers):
            if "tbot_sheduler" in str(type(handler).__module__):
                root.removeHandler(handler)

    def test_setup_logging_creates_handlers(self):
        """Test that setup_logging adds handlers to root logger."""
        # Reset root logger state
        root = logging.getLogger()
        old_handlers = list(root.handlers)
        root.handlers.clear()

        from tbot_sheduler.core.logging import setup_logging
        setup_logging()

        # Should have at least stdout + error + info handlers
        assert len(root.handlers) >= 3

        # Restore
        root.handlers.clear()
        for h in old_handlers:
            root.addHandler(h)

    def test_logging_level(self):
        """Test logging level is set from config."""
        from tbot_sheduler.core.config import LOG_LEVEL
        assert LOG_LEVEL in ("DEBUG", "INFO", "WARNING", "ERROR")

    def test_logging_suppresses_noisy_libraries(self):
        """Test that httpx/httpcore loggers are set to WARNING."""
        from tbot_sheduler.core.logging import setup_logging
        setup_logging()

        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
