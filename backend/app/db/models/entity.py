import enum
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import CHAR, Boolean, Date, DateTime, Enum, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SourceSystem(str, enum.Enum):
    netsuite = "netsuite"
    xero = "xero"
    manual = "manual"
    bigquery = "bigquery"


class CoaType(str, enum.Enum):
    netsuite = "netsuite"
    xero = "xero"
    custom = "custom"


class ConsolidationMethod(str, enum.Enum):
    full = "full"
    equity = "equity"
    none = "none"


class Entity(Base):
    __tablename__ = "entities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    name: Mapped[str | None] = mapped_column(String(200))
    source_system: Mapped[SourceSystem | None] = mapped_column(
        Enum(SourceSystem, name="source_system")
    )
    source_entity_id: Mapped[str | None] = mapped_column(String(100))
    parent_entity_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id")
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    currency: Mapped[str] = mapped_column(CHAR(3), default="AUD")
    coa_type: Mapped[CoaType | None] = mapped_column(
        Enum(CoaType, name="coa_type")
    )
    consolidation_method: Mapped[ConsolidationMethod] = mapped_column(
        Enum(ConsolidationMethod, name="consolidation_method"),
        default=ConsolidationMethod.full,
    )
    acquisition_date: Mapped[date | None] = mapped_column(Date)
