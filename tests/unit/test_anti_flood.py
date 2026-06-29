"""Unit tests for anti-flood."""
from __future__ import annotations

import time

import pytest

from tbot_sheduler.core.security import AntiFlood


class TestAntiFlood:
    """Test AntiFlood rate limiter."""

    def test_first_action_allowed(self):
        """Test first action is always allowed."""
        af = AntiFlood(cooldown_seconds=5)
        assert af.check(1001) is True

    def test_second_action_blocked(self):
        """Test second action within cooldown is blocked."""
        af = AntiFlood(cooldown_seconds=5)
        assert af.check(1002) is True
        assert af.check(1002) is False

    def test_different_users_independent(self):
        """Test different users have separate cooldowns."""
        af = AntiFlood(cooldown_seconds=5)
        assert af.check(2001) is True
        assert af.check(2002) is True
        # Both users' second action within cooldown
        assert af.check(2001) is False
        assert af.check(2002) is False

    def test_cooldown_expires(self):
        """Test cooldown expires after the set time."""
        af = AntiFlood(cooldown_seconds=1)
        assert af.check(3001) is True
        assert af.check(3001) is False  # Blocked
        # Wait for cooldown
        time.sleep(1.1)
        assert af.check(3001) is True  # Allowed again

    def test_cleanup(self):
        """Test cleanup removes stale entries."""
        af = AntiFlood(cooldown_seconds=1)
        af.check(4001)
        af.check(4002)
        assert 4001 in af._last_action
        assert 4002 in af._last_action

        af.cleanup()
        # Both should be recent, so they remain
        assert 4001 in af._last_action
        assert 4002 in af._last_action

    def test_cooldown_custom_value(self):
        """Test custom cooldown value."""
        af = AntiFlood(cooldown_seconds=10)
        assert af.check(5001) is True
        assert af.check(5001) is False
        # Even after 5 seconds, still blocked
        time.sleep(0.5)
        assert af.check(5001) is False

    def test_auto_cleanup_on_check_count(self):
        """Test automatic cleanup triggers every 1000th check."""
        af = AntiFlood(cooldown_seconds=1)
        # Simulate 1000 different users — triggers cleanup on 1000th
        for i in range(500):
            af.check(6000 + i)
        assert len(af._last_action) == 500
        assert af._check_count == 500

        # Add more to reach 1000 — cleanup runs but nothing is stale
        for i in range(500, 1000):
            af.check(6000 + i)
        assert af._check_count == 0  # Reset after cleanup
        # All entries are recent, so dict still has ~1000 entries
        assert len(af._last_action) >= 900

    def test_auto_cleanup_removes_stale(self):
        """Test auto-cleanup removes entries older than 1 hour."""
        af = AntiFlood(cooldown_seconds=1)

        # Add a user and manually age their entry
        af.check(7001)
        af._last_action[7001] = time.monotonic() - 4000  # > 1 hour ago

        # Add 999 more users to trigger cleanup
        for i in range(1, 1000):
            af.check(8000 + i)

        # Stale entry should be removed
        assert 7001 not in af._last_action
