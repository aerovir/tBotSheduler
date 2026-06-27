from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Integer, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from tbot_sheduler.core.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    slot_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    booking_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    details: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action={self.action})>"
