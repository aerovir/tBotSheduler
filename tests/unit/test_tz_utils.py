"""Tests for timezone utilities."""
from __future__ import annotations

from tbot_sheduler.core.tz_utils import (
    utc_to_tz, tz_to_utc, format_slot_time, get_available_tz_names,
)


class TestTimezoneUtils:
    """Test timezone conversion utilities."""

    def test_utc_to_moscow(self):
        """Test UTC to Moscow (+3)."""
        assert utc_to_tz(10, "Europe/Moscow") == 13

    def test_utc_to_vladivostok(self):
        """Test UTC to Vladivostok (+10)."""
        assert utc_to_tz(10, "Asia/Vladivostok") == 20

    def test_utc_to_midnight_wrap(self):
        """Test UTC hour wraps around correctly."""
        assert utc_to_tz(22, "Europe/Moscow") == 1  # 22+3=25 -> 1

    def test_moscow_to_utc(self):
        """Test Moscow to UTC (-3)."""
        assert tz_to_utc(13, "Europe/Moscow") == 10

    def test_roundtrip(self):
        """Test UTC -> TZ -> UTC preserves value."""
        for tz in ["Europe/Moscow", "Asia/Vladivostok", "UTC"]:
            for h in range(0, 24):
                local = utc_to_tz(h, tz)
                back = tz_to_utc(local, tz)
                assert back == h, f"Roundtrip failed for {tz} at hour {h}"

    def test_get_available_tz(self):
        """Test available timezones list."""
        tz_list = get_available_tz_names()
        assert "Europe/Moscow" in tz_list
        assert "UTC" in tz_list
        assert "Asia/Vladivostok" in tz_list

    def test_format_slot_time_utc(self):
        """Test slot time formatting in UTC."""
        result = format_slot_time(10, 11, None)
        assert "10:00" in result
        assert "UTC" in result

    def test_format_slot_time_msk(self):
        """Test slot time formatting in Moscow time."""
        result = format_slot_time(10, 11, "Europe/Moscow")
        assert "13" in result  # 10+3=13
        assert "Москва" in result or "Moscow" in result
