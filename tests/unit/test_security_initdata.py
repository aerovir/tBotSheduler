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
    secret_key = hmac.new(
        b"WebAppData", bot_token.encode(), hashlib.sha256
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
        """Test initData with very old auth_date."""
        # Generate with old date
        data = {
            "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
            "user": '{"id":12345}',
            "auth_date": "1000000",  # Year 1970
            "hash": "dummy",
        }
        # We need valid hash for this specific data
        secret_key = hmac.new(
            b"WebAppData", self.TEST_TOKEN.encode(), hashlib.sha256
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
        # Should be valid (we don't check expiry in basic validation)
        # But we should check auth_date is present
        assert result is not None
        assert result.get("auth_date") == "1000000"

    def test_empty_init_data(self):
        """Test empty initData returns None."""
        result = validate_init_data("", self.TEST_TOKEN)
        assert result is None
