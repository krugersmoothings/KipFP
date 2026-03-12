import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class VersionType(str, enum.Enum):
    budget = "budget"
    forecast = "forecast"
    scenario = "scenario"


class VersionStatus(str, enum.Enum):
    draft = "draft"
    approved = "approved"
    locked = "locked"


class BudgetVersion(Base):
    __tablename__ = "budget_versions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    fy_year: Mapped[int] = mapped_column(Integer, nullable=False)
    version_type: Mapped[VersionType] = mapped_column(
        Enum(VersionType, name="version_type"), default=VersionType.budget
    )
    status: Mapped[VersionStatus] = mapped_column(
        Enum(VersionStatus, name="version_status"), default=VersionStatus.draft
    )
    base_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id")
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ModelAssumption(Base):
    __tablename__ = "model_assumptions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    budget_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id")
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    assumption_key: Mapped[str] = mapped_column(String(100), nullable=False)
    assumption_value: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
