import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SiteBudgetDriverType(str, enum.Enum):
    manual = "manual"
    occupancy_rate = "occupancy_rate"
    per_dog_night = "per_dog_night"
    headcount_x_rate = "headcount_x_rate"
    pct_revenue = "pct_revenue"


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str | None] = mapped_column(String(20), unique=True)
    name: Mapped[str | None] = mapped_column(String(200))
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    state: Mapped[str | None] = mapped_column(String(3))
    opened_date: Mapped[datetime | None] = mapped_column(Date)
    closed_date: Mapped[datetime | None] = mapped_column(Date)
    capacity_dogs: Mapped[int | None] = mapped_column(Integer)
    netsuite_location_id: Mapped[str | None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class SiteBudgetEntry(Base):
    __tablename__ = "site_budget_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id")
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    model_line_item: Mapped[str | None] = mapped_column(String(100))
    week_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weekly_periods.id")
    )
    amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    driver_type: Mapped[SiteBudgetDriverType | None] = mapped_column(
        Enum(SiteBudgetDriverType, name="site_budget_driver_type")
    )
    driver_params: Mapped[dict | None] = mapped_column(JSONB)
    entered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
