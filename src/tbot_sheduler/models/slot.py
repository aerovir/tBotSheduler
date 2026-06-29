from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Integer, String, Date, Time, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tbot_sheduler.core.database import Base

if TYPE_CHECKING:
    from tbot_sheduler.models.admin import Admin
    from tbot_sheduler.models.booking import Booking
    from tbot_sheduler.models.channel import Channel


class Slot(Base):
    __tablename__ = "slot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    channel_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("channel.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    # Relationships
    channel: Mapped["Channel"] = relationship("Channel", back_populates="slots")
    created_by_admin: Mapped[Optional["Admin"]] = relationship(
        "Admin", backref="created_slots"
    )
    bookings: Mapped[list["Booking"]] = relationship(
        "Booking", back_populates="slot", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "channel_id", "date", "start_time",
            name="uq_slot_channel_date_time"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Slot(id={self.id}, channel_id={self.channel_id}, "
            f"date={self.date}, start={self.start_time})>"
        )
