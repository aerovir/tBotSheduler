"""Security utilities: initData validation, anti-flood."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse
from collections import deque

logger = logging.getLogger(__name__)


def validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram Web App initData using HMAC-SHA256.

    Args:
        init_data: Raw initData string from Telegram.WebApp.initData
        bot_token: Bot token used to compute the secret key

    Returns:
        Parsed initData dict if valid, None if tampered.
    """
    if not init_data or not bot_token:
        return None

    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    hash_received = parsed.pop("hash", None)

    if not hash_received:
        return None

    # Compute secret key: HMAC-SHA256(WebAppData, bot_token)
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
    ).digest()

    # Build data check string: sorted key=value lines
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # Compute expected hash
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if hmac.compare_digest(expected_hash, hash_received):
        return parsed

    return None


class AntiFlood:
    """Anti-flood: limit actions per user to 1 per N seconds.

    Uses in-memory dict with timestamps.
    """

    def __init__(self, cooldown_seconds: int = 5) -> None:
        self._cooldown = cooldown_seconds
        self._last_action: dict[int, float] = {}

    def check(self, user_id: int) -> bool:
        """Check if user can perform an action.

        Returns True if allowed, False if within cooldown.
        """
        now = time.monotonic()
        last = self._last_action.get(user_id, 0)
        if now - last < self._cooldown:
            logger.warning("Anti-flood triggered for user %d", user_id)
            return False
        self._last_action[user_id] = now
        return True

    def cleanup(self) -> None:
        """Remove stale entries older than 1 hour."""
        now = time.monotonic()
        stale = [
            uid
            for uid, ts in self._last_action.items()
            if now - ts > 3600
        ]
        for uid in stale:
            del self._last_action[uid]


# Global anti-flood instance
anti_flood = AntiFlood()
