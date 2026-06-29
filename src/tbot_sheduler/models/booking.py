from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Integer, String, Text, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tbot_sheduler.core.database import Base

if TYPE_CHECKING:
    from tbot_sheduler.models.slot import Slot
    from tbot_sheduler.models.notification import Notification


class Booking(Base):
    __tablename__ = "booking"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("slot.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    notify_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=10)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    # Relationships
    slot: Mapped["Slot"] = relationship("Slot", back_populates="bookings")
    notifications: Mapped[list["Notification"]] = relationship(
        "Notification", back_populates="booking", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint(
            "user_id", "slot_id",
            name="uq_booking_user_slot"
        ),
        UniqueConstraint(
            "slot_id",
            name="uq_booking_slot"
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<Booking(id={self.id}, user_id={self.user_id}, "
            f"slot_id={self.slot_id})>"
        )
