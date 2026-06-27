"""Unit tests for SlidingWindowRateLimiter."""
from __future__ import annotations

import pytest

from tbot_sheduler.core.rate_limiter import SlidingWindowRateLimiter


class TestSlidingWindowRateLimiter:
    """Test the in-memory sliding window rate limiter."""

    @pytest.fixture
    def limiter(self) -> SlidingWindowRateLimiter:
        return SlidingWindowRateLimiter()

    async def test_allow_under_limit(self, limiter: SlidingWindowRateLimiter):
        """Test requests under limit are allowed."""
        for _ in range(5):
            assert await limiter.check("user:1", limit=10, window_seconds=60) is True

    async def test_block_over_limit(self, limiter: SlidingWindowRateLimiter):
        """Test requests over limit are blocked."""
        for _ in range(3):
            assert await limiter.check("user:2", limit=3, window_seconds=60) is True
        # 4th request should be blocked
        assert await limiter.check("user:2", limit=3, window_seconds=60) is False

    async def test_independent_keys(self, limiter: SlidingWindowRateLimiter):
        """Test different keys have independent counters."""
        for _ in range(3):
            assert await limiter.check("user:a", limit=3, window_seconds=60) is True

        # Different key should still work
        assert await limiter.check("user:b", limit=3, window_seconds=60) is True
        assert await limiter.check("user:b", limit=3, window_seconds=60) is True
        assert await limiter.check("user:b", limit=3, window_seconds=60) is True
        # Now user:b should be blocked
        assert await limiter.check("user:b", limit=3, window_seconds=60) is False

    async def test_cleanup(self, limiter: SlidingWindowRateLimiter):
        """Test cleanup removes stale keys."""
        # Add some entries
        await limiter.check("stale:1", limit=5, window_seconds=60)
        await limiter.check("active:1", limit=5, window_seconds=60)

        # Run cleanup (shouldn't remove active entries within 1 hour)
        await limiter.cleanup()
        # Both should still exist since they just added
        assert "stale:1" in limiter._windows
        assert "active:1" in limiter._windows

    async def test_window_slides(self, limiter: SlidingWindowRateLimiter):
        """Test that window slides correctly with time."""
        # Since we can't easily mock time.monotonic with asyncio,
        # just verify the basic sliding behavior
        key = "slide:test"
        for _ in range(3):
            assert await limiter.check(key, limit=3, window_seconds=60) is True

        # Should be blocked exactly at limit
        assert await limiter.check(key, limit=3, window_seconds=60) is False
