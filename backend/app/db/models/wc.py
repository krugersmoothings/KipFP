import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WcDriverType(str, enum.Enum):
    dso = "dso"
    dpo = "dpo"
    dii = "dii"
    fixed_balance = "fixed_balance"
    pct_revenue = "pct_revenue"


class WcDriver(Base):
    __tablename__ = "wc_drivers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    budget_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id"), nullable=False
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    driver_type: Mapped[WcDriverType | None] = mapped_column(
        Enum(WcDriverType, name="wc_driver_type")
    )
    base_days: Mapped[float | None] = mapped_column(Numeric(6, 2))
    seasonal_factors: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)
    last_updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    last_updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
