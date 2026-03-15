import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, Integer, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ServiceType(str, enum.Enum):
    boarding = "boarding"
    daycare = "daycare"
    grooming = "grooming"
    wash = "wash"
    training = "training"


class SitePetDay(Base):
    """Daily actuals from BigQuery by location and service type."""

    __tablename__ = "site_pet_days"
    __table_args__ = (
        UniqueConstraint(
            "location_id", "date", "service_type",
            name="uq_site_pet_days_loc_date_svc",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    location_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    service_type: Mapped[ServiceType] = mapped_column(
        Enum(ServiceType, name="pet_service_type"), nullable=False
    )
    pet_days: Mapped[int] = mapped_column(Integer, nullable=False)
    revenue_aud: Mapped[float | None] = mapped_column(Numeric(12, 2))
    sync_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_runs.id")
    )
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
