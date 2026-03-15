"""Debt waterfall engine.

For each active debt facility, iterates through periods to calculate
opening balance → interest → repayment → closing balance.
Writes results to the debt_schedules table.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.debt import AmortType, DebtFacility, DebtSchedule, InterestCalcMethod
from app.db.models.period import Period

logger = logging.getLogger(__name__)


@dataclass
class DebtPeriodRow:
    facility_id: uuid.UUID
    period_id: uuid.UUID
    opening_balance: Decimal
    drawdown: Decimal
    repayment: Decimal
    closing_balance: Decimal
    interest_expense: Decimal
    interest_rate_applied: Decimal


@dataclass
class DebtWaterfallResult:
    rows: list[DebtPeriodRow] = field(default_factory=list)

    def total_interest_by_period(self) -> dict[uuid.UUID, Decimal]:
        totals: dict[uuid.UUID, Decimal] = {}
        for r in self.rows:
            totals[r.period_id] = totals.get(r.period_id, Decimal("0")) + r.interest_expense
        return totals

    def total_repayment_by_period(self) -> dict[uuid.UUID, Decimal]:
        totals: dict[uuid.UUID, Decimal] = {}
        for r in self.rows:
            totals[r.period_id] = totals.get(r.period_id, Decimal("0")) + r.repayment
        return totals

    def total_drawdown_by_period(self) -> dict[uuid.UUID, Decimal]:
        totals: dict[uuid.UUID, Decimal] = {}
        for r in self.rows:
            totals[r.period_id] = totals.get(r.period_id, Decimal("0")) + r.drawdown
        return totals

    def closing_balance_by_facility_period(
        self,
    ) -> dict[tuple[uuid.UUID, uuid.UUID], Decimal]:
        return {
            (r.facility_id, r.period_id): r.closing_balance for r in self.rows
        }

    def total_closing_by_period(self) -> dict[uuid.UUID, Decimal]:
        totals: dict[uuid.UUID, Decimal] = {}
        for r in self.rows:
            totals[r.period_id] = totals.get(r.period_id, Decimal("0")) + r.closing_balance
        return totals


async def calculate_debt_waterfall(
    db: AsyncSession,
    version_id: uuid.UUID,
    periods: list[Period],
    entity_ids: set[uuid.UUID] | None = None,
) -> DebtWaterfallResult:
    """Build debt schedules for all active facilities and persist to DB.

    Args:
        db: active session (will flush but NOT commit)
        version_id: budget version
        periods: FY periods in fy_month order
        entity_ids: optional filter
    """
    q = select(DebtFacility).where(DebtFacility.is_active.is_(True))
    if entity_ids:
        q = q.where(DebtFacility.entity_id.in_(entity_ids))
    q = q.order_by(DebtFacility.sort_order)

    result = await db.execute(q)
    facilities = result.scalars().all()

    if not facilities:
        return DebtWaterfallResult()

    await db.execute(
        delete(DebtSchedule).where(
            DebtSchedule.budget_version_id == version_id,
            DebtSchedule.period_id.in_([p.id for p in periods]),
        )
    )

    waterfall = DebtWaterfallResult()

    for fac in facilities:
        opening = Decimal(str(fac.opening_balance))
        annual_rate = Decimal(str(fac.base_rate or 0)) + Decimal(str(fac.margin or 0))

        for period in periods:
            if fac.maturity_date and period.period_start and period.period_start > fac.maturity_date:
                interest = Decimal("0")
                # FIX(M17): P&I loans should repay remaining balance at maturity
                if opening > Decimal("0") and fac.amort_type == AmortType.principal_and_interest:
                    repayment = opening
                else:
                    repayment = Decimal("0")
                drawdown = Decimal("0")
                closing = opening - repayment
            else:
                # FIX(M16): respect interest_calc_method (daily vs monthly)
                if fac.interest_calc_method == InterestCalcMethod.daily and period.period_start and period.period_end:
                    days_in_period = (period.period_end - period.period_start).days + 1
                    interest = opening * annual_rate * Decimal(str(days_in_period)) / Decimal("365")
                else:
                    interest = opening * annual_rate / Decimal("12")

                if fac.amort_type == AmortType.interest_only:
                    repayment = Decimal("0")
                elif fac.amort_type == AmortType.bullet:
                    if (
                        fac.maturity_date
                        and period.period_end
                        and period.period_end >= fac.maturity_date
                    ):
                        repayment = opening
                    else:
                        repayment = Decimal("0")
                else:
                    repayment = Decimal(str(fac.monthly_repayment or 0))

                repayment = min(repayment, opening)
                drawdown = Decimal("0")
                closing = opening - repayment + drawdown

            rate_applied = annual_rate

            row = DebtPeriodRow(
                facility_id=fac.id,
                period_id=period.id,
                opening_balance=opening,
                drawdown=drawdown,
                repayment=repayment,
                closing_balance=closing,
                interest_expense=interest,
                interest_rate_applied=rate_applied,
            )
            waterfall.rows.append(row)

            db.add(DebtSchedule(
                facility_id=fac.id,
                budget_version_id=version_id,
                period_id=period.id,
                opening_balance=float(opening),
                drawdown=float(drawdown),
                repayment=float(repayment),
                closing_balance=float(closing),
                interest_expense=float(interest),
                interest_rate_applied=float(rate_applied),
            ))

            opening = closing

    await db.flush()

    logger.info(
        "Debt waterfall: %d facilities × %d periods = %d rows",
        len(facilities),
        len(periods),
        len(waterfall.rows),
    )
    return waterfall
