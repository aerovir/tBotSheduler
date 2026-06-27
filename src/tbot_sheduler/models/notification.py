from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Integer, String, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tbot_sheduler.core.database import Base

if TYPE_CHECKING:
    from tbot_sheduler.models.booking import Booking


class Notification(Base):
    __tablename__ = "notification"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    booking_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("booking.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    notify_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    job_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    booking: Mapped["Booking"] = relationship("Booking", back_populates="notifications")

    __table_args__ = (
        Index("ix_notification_notify_sent", "notify_at", "sent"),
    )

    def __repr__(self) -> str:
        return (
            f"<Notification(id={self.id}, booking_id={self.booking_id}, "
            f"sent={self.sent})>"
        )
