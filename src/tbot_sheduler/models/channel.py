from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from tbot_sheduler.core.database import Base


class Channel(Base):
    __tablename__ = "channel"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chat_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(256), nullable=True)
    owner_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("admin.id", ondelete="CASCADE"), nullable=False
    )
    booking_horizon_days: Mapped[int] = mapped_column(
        Integer, nullable=False, default=14
    )
    default_notify_minutes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=10
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<Channel(id={self.id}, chat_id={self.chat_id}, title={self.title})>"
