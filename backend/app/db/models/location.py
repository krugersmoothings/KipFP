import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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


class PropertyMapping(Base):
    __tablename__ = "property_mappings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bigquery_property_id: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    bigquery_property_name: Mapped[str | None] = mapped_column(String(200))
    bigquery_url_slug: Mapped[str | None] = mapped_column(String(100))
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    notes: Mapped[str | None] = mapped_column(Text)


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


class SiteBudgetAssumption(Base):
    __tablename__ = "site_budget_assumptions"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "location_id",
            name="uq_site_budget_assumptions_version_location",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    fy_year: Mapped[int] = mapped_column(Integer, nullable=False)
    # Revenue drivers
    price_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.03)
    pet_day_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.02)
    bath_price: Mapped[float | None] = mapped_column(Numeric(8, 2))
    other_services_per_pet_day: Mapped[float | None] = mapped_column(Numeric(8, 4))
    membership_pct_revenue: Mapped[float | None] = mapped_column(Numeric(6, 4))
    # Labour drivers
    mpp_mins: Mapped[float | None] = mapped_column(Numeric(6, 2))
    min_daily_hours: Mapped[float | None] = mapped_column(Numeric(6, 2))
    wage_increase_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.05)
    # Fixed cost drivers
    cogs_pct: Mapped[float | None] = mapped_column(Numeric(6, 4))
    rent_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2))
    rent_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.03)
    utilities_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2))
    utilities_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.03)
    rm_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2))
    rm_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.05)
    it_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2))
    it_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.05)
    general_monthly: Mapped[float | None] = mapped_column(Numeric(10, 2))
    general_growth_pct: Mapped[float | None] = mapped_column(Numeric(6, 4), default=0.05)
    advertising_pct_revenue: Mapped[float | None] = mapped_column(Numeric(6, 4))
    # Metadata
    assumptions_locked: Mapped[bool] = mapped_column(Boolean, default=False)
    last_updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    last_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class SiteWeeklyBudget(Base):
    __tablename__ = "site_weekly_budget"
    __table_args__ = (
        UniqueConstraint(
            "version_id", "location_id", "week_id",
            name="uq_site_weekly_budget_version_loc_week",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id"), nullable=False
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    week_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("weekly_periods.id"), nullable=False
    )
    # Prior year inputs
    prior_year_pet_days_boarding: Mapped[int | None] = mapped_column(Integer)
    prior_year_pet_days_daycare: Mapped[int | None] = mapped_column(Integer)
    prior_year_pet_days_grooming: Mapped[int | None] = mapped_column(Integer)
    prior_year_pet_days_wash: Mapped[int | None] = mapped_column(Integer)
    prior_year_pet_days_training: Mapped[int | None] = mapped_column(Integer)
    prior_year_revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    # Calculated outputs
    budget_pet_days_boarding: Mapped[int | None] = mapped_column(Integer)
    budget_pet_days_daycare: Mapped[int | None] = mapped_column(Integer)
    budget_pet_days_grooming: Mapped[int | None] = mapped_column(Integer)
    budget_pet_days_wash: Mapped[int | None] = mapped_column(Integer)
    budget_pet_days_training: Mapped[int | None] = mapped_column(Integer)
    budget_revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_labour: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_cogs: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_rent: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_utilities: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_rm: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_it: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_general: Mapped[float | None] = mapped_column(Numeric(12, 2))
    budget_advertising: Mapped[float | None] = mapped_column(Numeric(12, 2))
    # Override
    is_overridden: Mapped[bool] = mapped_column(Boolean, default=False)
    override_revenue: Mapped[float | None] = mapped_column(Numeric(12, 2))
    override_labour: Mapped[float | None] = mapped_column(Numeric(12, 2))
    calculated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
