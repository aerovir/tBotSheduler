"""Security utilities: initData validation, anti-flood."""
from __future__ import annotations

import hashlib
import hmac
import logging
import time
import urllib.parse
from collections import deque

logger = logging.getLogger(__name__)


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 86400,
) -> dict | None:
    """Validate Telegram Web App initData using HMAC-SHA256.

    Проверяет HMAC-подпись и срок действия auth_date.
    Telegram рекомендует отклонять initData старше 24 часов (86400 сек)
    или 5 минут (300 сек) для операций записи.

    Args:
        init_data: Raw initData string from Telegram.WebApp.initData
        bot_token: Bot token used to compute the secret key
        max_age_seconds: Maximum age of auth_date in seconds.
                         Default 86400 (24h). Use 300 for write operations.

    Returns:
        Parsed initData dict if valid, None if tampered or expired.
    """
    if not init_data or not bot_token:
        return None

    parsed = dict(urllib.parse.parse_qsl(init_data, keep_blank_values=True))
    hash_received = parsed.pop("hash", None)

    if not hash_received:
        return None

    # Compute secret key: HMAC-SHA256(bot_token, "WebAppData")
    # Per Telegram spec: key=bot_token, message="WebAppData"
    secret_key = hmac.new(
        bot_token.encode(), b"WebAppData", hashlib.sha256
    ).digest()

    # Build data check string: sorted key=value lines
    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(parsed.items())
    )

    # Compute expected hash
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected_hash, hash_received):
        return None

    # Проверка auth_date — защита от replay-атак
    auth_date_str = parsed.get("auth_date")
    if not auth_date_str:
        logger.warning("validate_init_data: missing auth_date")
        return None

    try:
        auth_date_ts = int(auth_date_str)
    except (ValueError, TypeError):
        logger.warning("validate_init_data: invalid auth_date: %s", auth_date_str)
        return None

    now = time.time()
    if auth_date_ts < now - max_age_seconds:
        logger.warning(
            "validate_init_data: expired auth_date (%d < %d)",
            auth_date_ts, now - max_age_seconds,
        )
        return None

    if auth_date_ts > now + 300:  # 5 min clock skew tolerance
        logger.warning(
            "validate_init_data: future auth_date (%d > %d)",
            auth_date_ts, now + 300,
        )
        return None

    return parsed


class AntiFlood:
    """Anti-flood: limit actions per user to 1 per N seconds.

    Uses in-memory dict with timestamps.
    """

    def __init__(self, cooldown_seconds: int = 5) -> None:
        self._cooldown = cooldown_seconds
        self._last_action: dict[int, float] = {}
        self._check_count = 0

    def check(self, user_id: int) -> bool:
        """Check if user can perform an action.

        Автоматически очищает устаревшие записи каждые 1000 проверок.

        Returns True if allowed, False if within cooldown.
        """
        now = time.monotonic()
        last = self._last_action.get(user_id, 0)
        if now - last < self._cooldown:
            logger.warning("Anti-flood triggered for user %d", user_id)
            return False
        self._last_action[user_id] = now

        # Periodic cleanup: every 1000th check remove stale entries
        self._check_count += 1
        if self._check_count >= 1000:
            self._check_count = 0
            self._cleanup(now)

        return True

    def _cleanup(self, now: float | None = None) -> None:
        """Remove stale entries older than 1 hour."""
        if now is None:
            now = time.monotonic()
        stale = [
            uid
            for uid, ts in self._last_action.items()
            if now - ts > 3600
        ]
        for uid in stale:
            del self._last_action[uid]
        if stale:
            logger.debug("AntiFlood cleanup: removed %d stale entries", len(stale))

    def cleanup(self) -> None:
        """Public cleanup method — maintained for external callers."""
        self._cleanup()


# Global anti-flood instance
anti_flood = AntiFlood()
