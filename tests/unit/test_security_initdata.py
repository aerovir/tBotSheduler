"""Unit tests for Web App initData validation."""
from __future__ import annotations

import hmac
import hashlib
import time
import urllib.parse

import pytest

from tbot_sheduler.core.security import validate_init_data


def _generate_valid_init_data(bot_token: str, user_id: int = 12345) -> str:
    """Generate a valid initData string for testing."""
    data = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": f'{{"id":{user_id},"first_name":"Test","last_name":"User"}}',
        "auth_date": str(int(time.time())),
        "hash": "",  # will be replaced
    }

    # Compute hash
    # Per Telegram spec: secret_key = HMAC-SHA256(bot_token, "WebAppData")
    secret_key = hmac.new(
        bot_token.encode(), b"WebAppData", hashlib.sha256
    ).digest()

    data_check_string = "\n".join(
        f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
    )
    expected_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    data["hash"] = expected_hash
    return urllib.parse.urlencode(data)


class TestValidateInitData:
    """Test initData validation."""

    TEST_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

    def test_valid_init_data_returns_user_data(self):
        """Test valid initData returns parsed data."""
        init_data = _generate_valid_init_data(self.TEST_TOKEN, user_id=55555)
        result = validate_init_data(init_data, self.TEST_TOKEN)
        assert result is not None
        assert "user" in result
        assert "query_id" in result

    def test_tampered_hash_returns_none(self):
        """Test tampered initData returns None."""
        init_data = _generate_valid_init_data(self.TEST_TOKEN)
        # Tamper with the data
        parsed = dict(urllib.parse.parse_qsl(init_data))
        parsed["user"] = '{"id":99999,"first_name":"Hacker"}'
        tampered = urllib.parse.urlencode(parsed)

        result = validate_init_data(tampered, self.TEST_TOKEN)
        assert result is None

    def test_missing_hash_returns_none(self):
        """Test initData without hash returns None."""
        data = "user=%7B%22id%22%3A123%7D&auth_date=1000000"
        result = validate_init_data(data, self.TEST_TOKEN)
        assert result is None

    def test_wrong_token_returns_none(self):
        """Test initData signed with different token returns None."""
        init_data = _generate_valid_init_data(self.TEST_TOKEN)
        result = validate_init_data(init_data, "wrong:token")
        assert result is None

    def test_expired_auth_date(self):
        """Test initData with very old auth_date is rejected."""
        # Generate with old date (Year 1970)
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":12345}',
            "auth_date": "1000000",
            "hash": "dummy",
        }
        # Compute valid hash for this data
        secret_key = hmac.new(
            self.TEST_TOKEN.encode(), b"WebAppData", hashlib.sha256
        ).digest()
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
        )
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        data["hash"] = expected_hash
        init_data = urllib.parse.urlencode(data)

        result = validate_init_data(init_data, self.TEST_TOKEN)
        # Now auth_date check is enforced — old date should be rejected
        assert result is None

    def test_empty_init_data(self):
        """Test empty initData returns None."""
        result = validate_init_data("", self.TEST_TOKEN)
        assert result is None

    def test_missing_auth_date_rejected(self):
        """Test initData without auth_date is rejected."""
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":12345,"first_name":"Test"}',
            "hash": "dummy",
        }
        # Compute valid hash (without auth_date)
        secret_key = hmac.new(
            self.TEST_TOKEN.encode(), b"WebAppData", hashlib.sha256
        ).digest()
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
        )
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        data["hash"] = expected_hash
        init_data = urllib.parse.urlencode(data)

        result = validate_init_data(init_data, self.TEST_TOKEN)
        assert result is None

    def test_future_auth_date_rejected(self):
        """Test initData with future auth_date is rejected."""
        future_ts = str(int(time.time()) + 3600)  # 1 hour in future
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":12345}',
            "auth_date": future_ts,
            "hash": "dummy",
        }
        secret_key = hmac.new(
            self.TEST_TOKEN.encode(), b"WebAppData", hashlib.sha256
        ).digest()
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
        )
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        data["hash"] = expected_hash
        init_data = urllib.parse.urlencode(data)

        result = validate_init_data(init_data, self.TEST_TOKEN)
        assert result is None

    def test_recent_auth_date_accepted(self):
        """Test initData with recent auth_date is valid."""
        recent_ts = str(int(time.time()) - 60)  # 1 minute ago
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":12345,"first_name":"Test"}',
            "auth_date": recent_ts,
            "hash": "dummy",
        }
        secret_key = hmac.new(
            self.TEST_TOKEN.encode(), b"WebAppData", hashlib.sha256
        ).digest()
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
        )
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        data["hash"] = expected_hash
        init_data = urllib.parse.urlencode(data)

        result = validate_init_data(init_data, self.TEST_TOKEN)
        assert result is not None
        assert result.get("auth_date") == recent_ts

    def test_custom_max_age_rejects_old_date(self):
        """Test custom max_age_seconds rejects auth_date that would be valid with default."""
        expired_ts = str(int(time.time()) - 600)  # 10 minutes ago
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":12345}',
            "auth_date": expired_ts,
            "hash": "dummy",
        }
        secret_key = hmac.new(
            self.TEST_TOKEN.encode(), b"WebAppData", hashlib.sha256
        ).digest()
        data_check_string = "\n".join(
            f"{k}={v}" for k, v in sorted(data.items()) if k != "hash"
        )
        expected_hash = hmac.new(
            secret_key, data_check_string.encode(), hashlib.sha256
        ).hexdigest()
        data["hash"] = expected_hash
        init_data = urllib.parse.urlencode(data)

        # With default max_age (86400) — should be valid (10 min < 24h)
        result_default = validate_init_data(init_data, self.TEST_TOKEN)
        assert result_default is not None

        # With strict max_age (120s) — should be rejected (10 min > 2 min)
        result_strict = validate_init_data(
            init_data, self.TEST_TOKEN, max_age_seconds=120
        )
        assert result_strict is None
