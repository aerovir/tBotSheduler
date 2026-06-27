"""Unit tests for health message formatting."""
from __future__ import annotations

from tbot_sheduler.bot.developer_handlers import format_uptime, format_health_message


class TestFormatUptime:
    """Test format_uptime function."""

    def test_zero_seconds(self):
        """Test 0 seconds."""
        assert format_uptime(0) == "0с"

    def test_only_seconds(self):
        """Test less than a minute."""
        result = format_uptime(45)
        assert result == "45с"

    def test_minutes_and_seconds(self):
        """Test minutes and seconds."""
        result = format_uptime(125)
        assert "2м" in result
        assert "5с" in result

    def test_hours_minutes_seconds(self):
        """Test hours, minutes, seconds."""
        result = format_uptime(3665)
        assert "1ч" in result
        assert "1м" in result
        assert "5с" in result

    def test_days_hours_minutes(self):
        """Test days, hours, minutes."""
        result = format_uptime(90061)
        assert "1д" in result
        assert "1ч" in result
        assert "1м" in result
        assert "1с" in result


class TestFormatHealthMessage:
    """Test format_health_message function."""

    def test_format_ok_status(self):
        """Test formatting of OK status."""
        health_data = {
            "status": "ok",
            "version": "0.1.0",
            "uptime_seconds": 3600,
            "response_time_ms": 45,
            "checks": {
                "database": {"status": "ok", "detail": "wal_mode=ON"},
                "bot": {"status": "ok", "detail": "running, job_queue_size=5"},
            },
        }
        result = format_health_message(health_data)
        assert "✅" in result
        assert "OK" in result
        assert "0.1.0" in result
        assert "1ч" in result
        assert "45 мс" in result
        assert "wal_mode=ON" in result
        assert "running" in result

    def test_format_degraded_status(self):
        """Test formatting of DEGRADED status."""
        health_data = {
            "status": "degraded",
            "version": "0.1.0",
            "uptime_seconds": 100,
            "response_time_ms": 200,
            "checks": {
                "disk": {"status": "degraded", "detail": "disk space < 1GB"},
            },
        }
        result = format_health_message(health_data)
        assert "⚠️" in result
        assert "DEGRADED" in result
        assert "disk space" in result

    def test_format_down_status(self):
        """Test formatting of DOWN status."""
        health_data = {
            "status": "down",
            "version": "0.1.0",
            "uptime_seconds": 50,
            "response_time_ms": 5000,
            "checks": {
                "telegram_api": {"status": "down", "detail": "Connection refused"},
            },
        }
        result = format_health_message(health_data)
        assert "❌" in result
        assert "DOWN" in result
        assert "Connection refused" in result

    def test_format_all_checks_labels(self):
        """Test all check types have proper labels."""
        health_data = {
            "status": "ok",
            "version": "0.1.0",
            "uptime_seconds": 0,
            "response_time_ms": 0,
            "checks": {
                "database": {"status": "ok", "detail": ""},
                "bot": {"status": "ok", "detail": ""},
                "telegram_api": {"status": "ok", "detail": ""},
                "disk": {"status": "ok", "detail": ""},
                "memory": {"status": "ok", "detail": ""},
                "scheduler": {"status": "ok", "detail": ""},
            },
        }
        result = format_health_message(health_data)
        assert "🗄️" in result
        assert "🤖" in result
        assert "📡" in result
        assert "💾" in result
        assert "🧠" in result
        assert "⏰" in result
