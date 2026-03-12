import enum
import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FacilityType(str, enum.Enum):
    property_loan = "property_loan"
    equipment_loan = "equipment_loan"
    vehicle_loan = "vehicle_loan"
    revolving = "revolving"
    overdraft = "overdraft"


class InterestRateType(str, enum.Enum):
    fixed = "fixed"
    variable = "variable"


class InterestCalcMethod(str, enum.Enum):
    daily = "daily"
    monthly = "monthly"


class AmortType(str, enum.Enum):
    interest_only = "interest_only"
    principal_and_interest = "principal_and_interest"
    bullet = "bullet"
    custom = "custom"


class DebtFacility(Base):
    __tablename__ = "debt_facilities"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    code: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entities.id"), nullable=False
    )
    facility_type: Mapped[FacilityType | None] = mapped_column(
        Enum(FacilityType, name="facility_type")
    )
    limit_amount: Mapped[float | None] = mapped_column(Numeric(18, 2))
    opening_balance: Mapped[float] = mapped_column(
        Numeric(18, 2), nullable=False
    )
    interest_rate_type: Mapped[InterestRateType | None] = mapped_column(
        Enum(InterestRateType, name="interest_rate_type")
    )
    base_rate: Mapped[float | None] = mapped_column(Numeric(8, 6))
    margin: Mapped[float] = mapped_column(Numeric(8, 6), default=0)
    interest_calc_method: Mapped[InterestCalcMethod] = mapped_column(
        Enum(InterestCalcMethod, name="interest_calc_method"),
        default=InterestCalcMethod.monthly,
    )
    amort_type: Mapped[AmortType | None] = mapped_column(
        Enum(AmortType, name="amort_type")
    )
    monthly_repayment: Mapped[float | None] = mapped_column(Numeric(18, 2))
    repayment_day: Mapped[int | None] = mapped_column(Integer)
    maturity_date: Mapped[date | None] = mapped_column(Date)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class DebtSchedule(Base):
    __tablename__ = "debt_schedules"
    __table_args__ = (
        Index("ix_debt_schedules_facility_period", "facility_id", "period_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("debt_facilities.id"), nullable=False
    )
    budget_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("budget_versions.id"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("periods.id"), nullable=False
    )
    opening_balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    drawdown: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    repayment: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    closing_balance: Mapped[float | None] = mapped_column(Numeric(18, 2))
    interest_expense: Mapped[float | None] = mapped_column(Numeric(18, 2))
    interest_rate_applied: Mapped[float | None] = mapped_column(Numeric(8, 6))
