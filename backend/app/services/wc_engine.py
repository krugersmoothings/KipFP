"""Working-capital schedule engine.

For each wc_driver row attached to a budget version, calculates the
closing balance per period based on driver type (DSO, DPO, DII, etc.)
and returns the movement (delta) for each period.
"""

from __future__ import annotations

import calendar
import logging
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.period import Period
from app.db.models.wc import WcDriver, WcDriverType

logger = logging.getLogger(__name__)


@dataclass
class WcPeriodResult:
    account_id: uuid.UUID
    entity_id: uuid.UUID
    period_id: uuid.UUID
    opening_balance: Decimal
    closing_balance: Decimal
    movement: Decimal


@dataclass
class WcScheduleResult:
    rows: list[WcPeriodResult] = field(default_factory=list)

    def movements_by_period(self) -> dict[uuid.UUID, Decimal]:
        """Net WC movement per period (positive = cash outflow)."""
        totals: dict[uuid.UUID, Decimal] = {}
        for r in self.rows:
            totals[r.period_id] = totals.get(r.period_id, Decimal("0")) + r.movement
        return totals

    def closing_by_account_period(
        self,
    ) -> dict[tuple[uuid.UUID, uuid.UUID], Decimal]:
        """(account_id, period_id) → closing_balance."""
        return {(r.account_id, r.period_id): r.closing_balance for r in self.rows}


def _days_in_month(period: Period) -> int:
    if period.period_start:
        return calendar.monthrange(
            period.period_start.year, period.period_start.month
        )[1]
    cal_year = period.fy_year - 1 if period.fy_month <= 6 else period.fy_year
    cal_month = (period.fy_month + 6) % 12 or 12
    return calendar.monthrange(cal_year, cal_month)[1]


async def calculate_wc_schedule(
    db: AsyncSession,
    version_id: uuid.UUID,
    periods: list[Period],
    revenue_by_entity_period: dict[tuple[uuid.UUID, uuid.UUID], Decimal],
    cogs_by_entity_period: dict[tuple[uuid.UUID, uuid.UUID], Decimal],
) -> WcScheduleResult:
    """Build the working-capital schedule for every wc_driver row.

    Args:
        db: active session
        version_id: budget version
        periods: FY periods in fy_month order
        revenue_by_entity_period: (entity_id, period_id) → revenue amount
        cogs_by_entity_period: (entity_id, period_id) → cogs amount (positive = cost)
    """
    result = await db.execute(
        select(WcDriver).where(WcDriver.budget_version_id == version_id)
    )
    drivers = result.scalars().all()

    if not drivers:
        return WcScheduleResult()

    schedule = WcScheduleResult()

    for drv in drivers:
        prior_closing = Decimal("0")

        for idx, period in enumerate(periods):
            seasonal = _seasonal_factor(drv, idx)
            effective_days = (
                Decimal(str(drv.base_days or 0)) * seasonal
            )
            dim = Decimal(str(_days_in_month(period)))

            key = (drv.entity_id, period.id)

            if drv.driver_type == WcDriverType.dso:
                rev = revenue_by_entity_period.get(key, Decimal("0"))
                closing = (rev / dim * effective_days) if dim else Decimal("0")

            elif drv.driver_type == WcDriverType.dpo:
                cost = cogs_by_entity_period.get(key, Decimal("0"))
                closing = (cost / dim * effective_days) if dim else Decimal("0")

            elif drv.driver_type == WcDriverType.dii:
                cost = cogs_by_entity_period.get(key, Decimal("0"))
                closing = (cost / dim * effective_days) if dim else Decimal("0")

            elif drv.driver_type == WcDriverType.fixed_balance:
                closing = Decimal(str(drv.base_days or 0))

            elif drv.driver_type == WcDriverType.pct_revenue:
                rev = revenue_by_entity_period.get(key, Decimal("0"))
                pct = Decimal(str(drv.base_days or 0)) / Decimal("100")
                closing = rev * pct

            else:
                closing = Decimal("0")

            movement = closing - prior_closing

            schedule.rows.append(
                WcPeriodResult(
                    account_id=drv.account_id,
                    entity_id=drv.entity_id,
                    period_id=period.id,
                    opening_balance=prior_closing,
                    closing_balance=closing,
                    movement=movement,
                )
            )
            prior_closing = closing

    logger.info(
        "WC schedule: %d drivers × %d periods = %d rows",
        len(drivers),
        len(periods),
        len(schedule.rows),
    )
    return schedule


def _seasonal_factor(drv: WcDriver, period_index: int) -> Decimal:
    """Pull seasonal multiplier for a given period index (0-11).

    Dict keys are 1-based (matching fy_month convention).
    """
    if not drv.seasonal_factors:
        return Decimal("1")
    factors = drv.seasonal_factors
    if isinstance(factors, list) and period_index < len(factors):
        return Decimal(str(factors[period_index]))
    if isinstance(factors, dict):
        # FIX(L32): prefer 1-based key (canonical); fall back to 0-based only
        val = factors.get(str(period_index + 1))
        if val is None:
            val = factors.get(str(period_index))
        if val is not None:
            return Decimal(str(val))
    return Decimal("1")
