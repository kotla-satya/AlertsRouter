from datetime import datetime, timezone

from sqlalchemy import String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class RouteSuppression(Base):
    __tablename__ = "route_suppressions"

    route_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    service: Mapped[str] = mapped_column(String(255), primary_key=True)
    last_routed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
