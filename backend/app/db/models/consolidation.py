import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ConsolidationStatus(str, enum.Enum):
    running = "running"
    success = "success"
    failed = "failed"


class ConsolidatedActual(Base):
    __tablename__ = "consolidated_actuals"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("periods.id"), nullable=False
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False
    )
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    amount: Mapped[float] = mapped_column(Numeric(18, 2), nullable=False, default=0)
    is_group_total: Mapped[bool] = mapped_column(Boolean, default=False)
    include_aasb16: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class ICEliminationRule(Base):
    __tablename__ = "ic_elimination_rules"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    label: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    account_code_a: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    account_code_b: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tolerance: Mapped[float] = mapped_column(Numeric(18, 2), default=10.00)
    notes: Mapped[str | None] = mapped_column(Text)


class ConsolidationRun(Base):
    __tablename__ = "consolidation_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("periods.id"), nullable=False
    )
    status: Mapped[ConsolidationStatus] = mapped_column(
        Enum(ConsolidationStatus, name="consolidation_status"),
        default=ConsolidationStatus.running,
    )
    bs_balanced: Mapped[bool | None] = mapped_column(Boolean)
    bs_variance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    ic_alerts: Mapped[str | None] = mapped_column(Text)
    error_detail: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
