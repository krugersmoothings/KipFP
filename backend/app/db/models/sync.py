import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SyncStatus(str, enum.Enum):
    running = "running"
    success = "success"
    partial = "partial"
    failed = "failed"


class SyncTrigger(str, enum.Enum):
    schedule = "schedule"
    manual = "manual"


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    source_system: Mapped[str | None] = mapped_column(
        Enum("netsuite", "xero", name="source_system", create_type=False)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[SyncStatus | None] = mapped_column(
        Enum(SyncStatus, name="sync_status")
    )
    records_upserted: Mapped[int] = mapped_column(Integer, default=0)
    error_detail: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[SyncTrigger] = mapped_column(
        Enum(SyncTrigger, name="sync_trigger"), default=SyncTrigger.manual
    )


class JeLine(Base):
    __tablename__ = "je_lines"
    __table_args__ = (
        Index("ix_je_lines_entity_period", "entity_id", "period_id"),
        Index("ix_je_lines_source_account", "source_account_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("periods.id"), nullable=False
    )
    source_account_code: Mapped[str] = mapped_column(
        String(100), nullable=False
    )
    source_account_name: Mapped[str | None] = mapped_column(String(200))
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False)
    sync_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sync_runs.id"), nullable=False
    )
    source_ref: Mapped[str | None] = mapped_column(String(200))
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("locations.id")
    )
