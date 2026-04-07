from datetime import datetime, timezone

from sqlalchemy import Boolean, String, Text, DateTime, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    service: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    group: Mapped[str] = mapped_column(String(255), name="group", nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    labels: Mapped[dict] = mapped_column(JSON, nullable=True, default=dict)
    suppressed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    is_routed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    routing_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
