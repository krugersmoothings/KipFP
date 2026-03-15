"""Site-level budget rollup service.

Reads all site_budget_entries for a budget version, applies weekly proration
using days_this_week_in_fy_month / 7.0 from weekly_periods, aggregates to
entity x month totals, and writes results into model_assumptions.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.budget import BudgetVersion, ModelAssumption
from app.db.models.entity import Entity
from app.db.models.location import Location, SiteBudgetEntry
from app.db.models.period import Period, WeeklyPeriod

logger = logging.getLogger(__name__)

SITE_LINE_ITEMS = [
    "boarding_revenue",
    "grooming_revenue",
    "other_revenue",
    "direct_wages",
    "direct_costs",
    "rent",
    "utilities",
    "repairs_maintenance",
    "it_systems",
    "general_admin",
    "advertising",
]

REVENUE_LINES = {"boarding_revenue", "grooming_revenue", "other_revenue"}


async def rollup_sites_to_entity(
    db: AsyncSession,
    version_id: uuid.UUID,
) -> dict:
    """Aggregate site budgets to entity-level monthly totals.

    Returns a summary dict with counts and totals.
    """
    version = await db.get(BudgetVersion, version_id)
    if version is None:
        raise ValueError(f"Budget version {version_id} not found")

    fy_year = version.fy_year

    # Load periods for the FY
    result = await db.execute(
        select(Period)
        .where(Period.fy_year == fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(result.scalars().all())
    if not periods:
        raise ValueError(f"No periods for FY{fy_year}")

    period_by_month: dict[int, Period] = {p.fy_month: p for p in periods}

    # Load weekly periods for the FY
    result = await db.execute(
        select(WeeklyPeriod).where(WeeklyPeriod.fy_year == fy_year)
    )
    weekly_periods = list(result.scalars().all())

    # Build week_id → (fy_month, proration_factor)
    week_proration: dict[uuid.UUID, tuple[int, Decimal]] = {}
    for wp in weekly_periods:
        if wp.fy_month is not None and wp.days_this_week_in_fy_month is not None:
            factor = Decimal(str(wp.days_this_week_in_fy_month)) / Decimal("7")
            week_proration[wp.id] = (wp.fy_month, factor)

    # Load locations with entity assignments
    result = await db.execute(
        select(Location).where(Location.is_active.is_(True))
    )
    locations = list(result.scalars().all())
    loc_entity: dict[uuid.UUID, uuid.UUID] = {}
    for loc in locations:
        if loc.entity_id:
            loc_entity[loc.id] = loc.entity_id

    # Load all site budget entries for this version
    result = await db.execute(
        select(SiteBudgetEntry).where(
            SiteBudgetEntry.version_id == version_id
        )
    )
    entries = list(result.scalars().all())

    if not entries:
        logger.info("No site budget entries for version %s", version_id)
        return {"entries": 0, "assumptions_written": 0}

    # Aggregate: (entity_id, fy_month, line_item) → Decimal
    aggregated: dict[tuple[uuid.UUID, int, str], Decimal] = defaultdict(
        lambda: Decimal("0")
    )

    for entry in entries:
        entity_id = loc_entity.get(entry.location_id)
        if entity_id is None:
            continue

        amount = Decimal(str(entry.amount or 0))
        line_item = entry.model_line_item or ""

        if entry.week_id and entry.week_id in week_proration:
            fy_month, factor = week_proration[entry.week_id]
            prorated = amount * factor
        elif entry.driver_params and "fy_month" in entry.driver_params:
            fy_month = int(entry.driver_params["fy_month"])
            prorated = amount
        else:
            continue

        aggregated[(entity_id, fy_month, line_item)] += prorated

    # Load entities for name mapping
    result = await db.execute(
        select(Entity).where(Entity.is_active.is_(True))
    )
    entity_map = {e.id: e for e in result.scalars().all()}

    # Write aggregated totals into model_assumptions
    now = datetime.now(timezone.utc)
    assumptions_written = 0

    # Group by entity → build assumption_value dicts per line_item
    entity_line_months: dict[tuple[uuid.UUID, str], dict[str, float]] = defaultdict(dict)
    for (entity_id, fy_month, line_item), total in aggregated.items():
        entity_line_months[(entity_id, line_item)][str(fy_month)] = float(total)

    for (entity_id, line_item), month_values in entity_line_months.items():
        assumption_key = f"site_rollup.{line_item}"

        result = await db.execute(
            select(ModelAssumption).where(
                ModelAssumption.budget_version_id == version_id,
                ModelAssumption.entity_id == entity_id,
                ModelAssumption.assumption_key == assumption_key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.assumption_value = month_values
            existing.updated_at = now
        else:
            db.add(ModelAssumption(
                budget_version_id=version_id,
                entity_id=entity_id,
                assumption_key=assumption_key,
                assumption_value=month_values,
                updated_at=now,
            ))
        assumptions_written += 1

    # Also write total revenue per entity per month for model consumption
    revenue_by_entity_month: dict[tuple[uuid.UUID, int], Decimal] = defaultdict(
        lambda: Decimal("0")
    )
    for (entity_id, fy_month, line_item), total in aggregated.items():
        if line_item in REVENUE_LINES:
            revenue_by_entity_month[(entity_id, fy_month)] += total

    for entity_id in {eid for eid, _ in revenue_by_entity_month}:
        entity = entity_map.get(entity_id)
        if not entity:
            continue

        month_values = {}
        for fy_month in range(1, 13):
            val = revenue_by_entity_month.get((entity_id, fy_month), Decimal("0"))
            month_values[str(fy_month)] = float(val)

        assumption_key = f"revenue.{entity.code}.manual"

        result = await db.execute(
            select(ModelAssumption).where(
                ModelAssumption.budget_version_id == version_id,
                ModelAssumption.entity_id == entity_id,
                ModelAssumption.assumption_key == assumption_key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.assumption_value = {"value": 0, **month_values}
            existing.updated_at = now
        else:
            db.add(ModelAssumption(
                budget_version_id=version_id,
                entity_id=entity_id,
                assumption_key=assumption_key,
                assumption_value={"value": 0, **month_values},
                updated_at=now,
            ))
        assumptions_written += 1

    await db.flush()

    summary = {
        "entries": len(entries),
        "assumptions_written": assumptions_written,
        "entities": len(set(eid for eid, _, _ in aggregated)),
    }
    logger.info(
        "Site rollup complete: %d entries → %d assumptions across %d entities",
        summary["entries"],
        summary["assumptions_written"],
        summary["entities"],
    )
    return summary
