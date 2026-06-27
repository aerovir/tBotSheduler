"""Waiting queue model for busy slots."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from tbot_sheduler.core.database import Base


class WaitingEntry(Base):
    """A user waiting for a slot to become free."""

    __tablename__ = "waiting_entry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("slot.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    __table_args__ = (
        UniqueConstraint("slot_id", "user_id", name="uq_waiting_slot_user"),
    )

    def __repr__(self) -> str:
        return f"<WaitingEntry(slot_id={self.slot_id}, user_id={self.user_id})>"
