"""Timezone utilities for user slot display."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, time as dt_time

# Common timezone offsets (UTC based)
TZ_OFFSETS: dict[str, int] = {
    "UTC": 0,
    "Europe/Kaliningrad": 2,
    "Europe/Moscow": 3,
    "Europe/Samara": 4,
    "Asia/Yekaterinburg": 5,
    "Asia/Omsk": 6,
    "Asia/Krasnoyarsk": 7,
    "Asia/Irkutsk": 8,
    "Asia/Yakutsk": 9,
    "Asia/Vladivostok": 10,
    "Asia/Magadan": 11,
    "Asia/Kamchatka": 12,
}


def utc_to_tz(utc_hour: int, tz_name: str) -> int:
    """Convert UTC hour to target timezone hour.

    Args:
        utc_hour: Hour in UTC (0-23)
        tz_name: Timezone name (e.g. 'Europe/Moscow')

    Returns:
        Hour in target timezone (0-23), wrapped around.
    """
    offset = TZ_OFFSETS.get(tz_name, 0)
    return (utc_hour + offset) % 24


def tz_to_utc(local_hour: int, tz_name: str) -> int:
    """Convert local timezone hour to UTC.

    Args:
        local_hour: Hour in local timezone (0-23)
        tz_name: Timezone name

    Returns:
        Hour in UTC (0-23), wrapped around.
    """
    offset = TZ_OFFSETS.get(tz_name, 0)
    return (local_hour - offset) % 24


def get_available_tz_names() -> list[str]:
    """Get list of available timezone names."""
    return list(TZ_OFFSETS.keys())


def format_slot_time(
    start_hour: int, end_hour: int, user_tz: str | None
) -> str:
    """Format slot time range in user's timezone."""
    if user_tz and user_tz in TZ_OFFSETS:
        start = utc_to_tz(start_hour, user_tz)
        end = utc_to_tz(end_hour, user_tz)
        return f"{start:02d}:00–{end:02d}:00 {user_tz.split('/')[-1]}"
    return f"{start_hour:02d}:00–{end_hour:02d}:00 UTC"
