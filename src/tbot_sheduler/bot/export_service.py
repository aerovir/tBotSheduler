"""Schedule export service (JSON/CSV)."""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from tbot_sheduler.models import Slot, Channel

logger = logging.getLogger(__name__)


async def export_schedule_json(
    db_session: AsyncSession, channel_id: int, from_date: date, to_date: date
) -> str:
    """Export schedule as formatted JSON."""
    result = await db_session.execute(
        select(Slot)
        .options(selectinload(Slot.bookings))
        .where(
            Slot.channel_id == channel_id,
            Slot.date >= from_date,
            Slot.date <= to_date,
            Slot.is_active == True,
        )
        .order_by(Slot.date, Slot.start_time)
    )
    slots = result.scalars().all()

    data = []
    for slot in slots:
        item = {
            "id": slot.id,
            "date": str(slot.date),
            "start_time": slot.start_time.strftime("%H:%M"),
            "end_time": slot.end_time.strftime("%H:%M"),
            "status": "booked" if slot.bookings else "available",
        }
        if slot.bookings:
            booking = slot.bookings[0]
            item["booked_by"] = {
                "user_id": booking.user_id,
                "user_name": booking.user_name,
            }
        data.append(item)

    return json.dumps(data, ensure_ascii=False, indent=2)


async def export_schedule_csv(
    db_session: AsyncSession, channel_id: int, from_date: date, to_date: date
) -> str:
    """Export schedule as CSV."""
    result = await db_session.execute(
        select(Slot)
        .options(selectinload(Slot.bookings))
        .where(
            Slot.channel_id == channel_id,
            Slot.date >= from_date,
            Slot.date <= to_date,
            Slot.is_active == True,
        )
        .order_by(Slot.date, Slot.start_time)
    )
    slots = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID", "Дата", "Начало", "Конец", "Статус", "Кто занял", "User ID"])

    for slot in slots:
        status = "booked" if slot.bookings else "available"
        user_name = slot.bookings[0].user_name if slot.bookings else ""
        user_id = slot.bookings[0].user_id if slot.bookings else ""
        writer.writerow([
            slot.id, str(slot.date),
            slot.start_time.strftime("%H:%M"),
            slot.end_time.strftime("%H:%M"),
            status, user_name, user_id,
        ])

    return output.getvalue()
