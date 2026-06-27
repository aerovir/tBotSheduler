from __future__ import annotations

import logging
import time
from collections import deque
from typing import Protocol

logger = logging.getLogger(__name__)


class RateLimiter(Protocol):
    """Protocol for rate limiters."""

    async def check(self, key: str, limit: int, window_seconds: int = 60) -> bool:
        """Returns True if request is allowed, False if rate limited."""
        ...


class SlidingWindowRateLimiter:
    """In-memory sliding window rate limiter per key.

    Structure:
    {key: deque[timestamp1, timestamp2, ...]}

    Thread-safe via asyncio.Lock.
    """

    def __init__(self) -> None:
        self._windows: dict[str, deque[float]] = {}
        self._lock = None  # Lazy init in async context

    async def _ensure_lock(self) -> None:
        if self._lock is None:
            import asyncio
            self._lock = asyncio.Lock()

    async def check(
        self, key: str, limit: int, window_seconds: int = 60
    ) -> bool:
        """Check if request is allowed. Returns True if under limit.

        Args:
            key: Identifier (e.g. user_id, API key ID)
            limit: Maximum number of requests in the window
            window_seconds: Time window in seconds

        Returns:
            True if request is allowed, False if rate limited.
        """
        await self._ensure_lock()
        assert self._lock is not None

        async with self._lock:
            now = time.monotonic()
            if key not in self._windows:
                self._windows[key] = deque()

            window = self._windows[key]

            # Remove expired entries
            while window and window[0] < now - window_seconds:
                window.popleft()

            if len(window) >= limit:
                return False  # Rate limited

            window.append(now)
            return True

    async def cleanup(self) -> None:
        """Remove stale entries (ids with empty windows older than 1 hour)."""
        await self._ensure_lock()
        assert self._lock is not None

        async with self._lock:
            now = time.monotonic()
            stale_keys = [
                key
                for key, window in self._windows.items()
                if not window or window[-1] < now - 3600
            ]
            for key in stale_keys:
                del self._windows[key]

            if stale_keys:
                logger.debug("Cleaned up %d stale rate limiter entries", len(stale_keys))
