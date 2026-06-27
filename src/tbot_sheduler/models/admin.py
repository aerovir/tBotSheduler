from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Integer, String, ForeignKey, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from tbot_sheduler.core.database import Base

if TYPE_CHECKING:
    from tbot_sheduler.models import AuditLog


class Admin(Base):
    __tablename__ = "admin"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(
        String(16), nullable=False, default="moderator"
    )
    added_by: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("admin.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=datetime.utcnow
    )

    # Relationships
    added_by_admin: Mapped[Optional["Admin"]] = relationship(
        "Admin", remote_side="Admin.id", backref="added_admins"
    )

    def __repr__(self) -> str:
        return f"<Admin(id={self.id}, user_id={self.user_id}, role={self.role})>"
