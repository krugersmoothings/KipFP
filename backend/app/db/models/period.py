import uuid
from datetime import date

from sqlalchemy import Boolean, Date, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Period(Base):
    __tablename__ = "periods"
    __table_args__ = (
        UniqueConstraint("fy_year", "fy_month", name="uq_periods_fy"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    fy_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fy_month: Mapped[int] = mapped_column(Integer, nullable=False)
    calendar_year: Mapped[int | None] = mapped_column(Integer)
    calendar_month: Mapped[int | None] = mapped_column(Integer)
    period_start: Mapped[date | None] = mapped_column(Date)
    period_end: Mapped[date | None] = mapped_column(Date)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=False)


class WeeklyPeriod(Base):
    __tablename__ = "weekly_periods"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    week_start_date: Mapped[date] = mapped_column(
        Date, unique=True, nullable=False
    )
    week_end_date: Mapped[date | None] = mapped_column(Date)
    fy_year: Mapped[int | None] = mapped_column(Integer)
    fy_month: Mapped[int | None] = mapped_column(Integer)
    fy_quarter: Mapped[int | None] = mapped_column(Integer)
    calendar_year: Mapped[int | None] = mapped_column(Integer)
    calendar_month: Mapped[int | None] = mapped_column(Integer)
    days_in_fy_month: Mapped[int | None] = mapped_column(Integer)
    days_this_week_in_fy_month: Mapped[int | None] = mapped_column(Integer)
    week_label: Mapped[str | None] = mapped_column(String(20))
