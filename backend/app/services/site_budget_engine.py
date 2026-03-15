"""Site-level operational budget engine.

Calculates weekly budgets for each site by applying growth assumptions
to prior-year pet-day actuals and deriving revenue, labour, and fixed costs.
"""

from __future__ import annotations

import logging
import math
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.models.budget import BudgetVersion
from app.db.models.location import (
    Location,
    SiteBudgetAssumption,
    SiteBudgetEntry,
    SiteWeeklyBudget,
)
from app.db.models.period import Period, WeeklyPeriod
from app.db.models.pet_days import SitePetDay
from app.db.models.sync import JeLine

logger = logging.getLogger(__name__)

SERVICE_TYPES = ["boarding", "daycare", "grooming", "wash", "training"]


def _d(v) -> Decimal:
    """Coerce a value to Decimal, treating None as 0."""
    if v is None:
        return Decimal("0")
    return Decimal(str(v))


async def _get_prior_year_pet_days(
    db: AsyncSession,
    location_id: uuid.UUID,
    prior_fy_year: int,
) -> dict[uuid.UUID, dict[str, int]]:
    """Load prior-year weekly pet days from site_pet_days.

    Returns {week_id: {service_type: count}} mapped via weekly_periods dates.
    """
    result = await db.execute(
        select(WeeklyPeriod)
        .where(WeeklyPeriod.fy_year == prior_fy_year)
        .order_by(WeeklyPeriod.week_start_date)
    )
    prior_weeks = result.scalars().all()
    if not prior_weeks:
        return {}

    date_min = prior_weeks[0].week_start_date
    date_max = max(w.week_end_date or w.week_start_date for w in prior_weeks)

    result = await db.execute(
        select(SitePetDay).where(
            SitePetDay.location_id == location_id,
            SitePetDay.date >= date_min,
            SitePetDay.date <= date_max,
        )
    )
    actuals = result.scalars().all()

    week_map: dict[uuid.UUID, dict[str, int]] = {}
    for w in prior_weeks:
        week_map[w.id] = {s: 0 for s in SERVICE_TYPES}

    for pd in actuals:
        for w in prior_weeks:
            end = w.week_end_date or w.week_start_date
            if w.week_start_date <= pd.date <= end:
                svc = pd.service_type.value
                if svc in week_map[w.id]:
                    week_map[w.id][svc] += pd.pet_days
                break

    return week_map


async def _get_prior_year_avg_price(
    db: AsyncSession,
    location_id: uuid.UUID,
    prior_fy_year: int,
) -> Decimal:
    """Average revenue per pet day from prior year actuals."""
    result = await db.execute(
        select(WeeklyPeriod).where(WeeklyPeriod.fy_year == prior_fy_year)
    )
    weeks = result.scalars().all()
    if not weeks:
        return Decimal("0")

    date_min = min(w.week_start_date for w in weeks)
    date_max = max(w.week_end_date or w.week_start_date for w in weeks)

    result = await db.execute(
        select(
            func.sum(SitePetDay.revenue_aud),
            func.sum(SitePetDay.pet_days),
        ).where(
            SitePetDay.location_id == location_id,
            SitePetDay.date >= date_min,
            SitePetDay.date <= date_max,
        )
    )
    row = result.one()
    total_rev, total_pd = row
    if not total_pd or total_pd == 0:
        return Decimal("0")
    return Decimal(str(total_rev)) / Decimal(str(total_pd))


async def _get_prior_year_avg_wage(
    db: AsyncSession,
    location_id: uuid.UUID,
    prior_fy_year: int,
) -> Decimal:
    """Average hourly wage derived from prior year OPEX-WAGES je_lines.

    Estimates by dividing total wages by estimated labour hours.
    Falls back to $35/hr if no data is available.
    """
    result = await db.execute(
        select(Period).where(Period.fy_year == prior_fy_year)
    )
    periods = result.scalars().all()
    if not periods:
        return Decimal("35")

    period_ids = [p.id for p in periods]

    result = await db.execute(
        select(func.sum(func.abs(JeLine.amount))).where(
            JeLine.location_id == location_id,
            JeLine.period_id.in_(period_ids),
            JeLine.source_account_name.ilike("%wage%"),
        )
    )
    total_wages = result.scalar()
    if not total_wages or total_wages == 0:
        return Decimal("35")

    # Rough estimate: 10 hours/day * 365 days ≈ 3650 labour hours/year
    # This is a simplification; real MPP-based hours would be more accurate
    estimated_hours = Decimal("3650")
    return Decimal(str(total_wages)) / estimated_hours


async def calculate_site_weekly_budget(
    version_id: uuid.UUID,
    location_id: uuid.UUID,
    db: AsyncSession | None = None,
) -> dict:
    """Calculate weekly budget for a single site.

    1. Load assumptions for this version/location
    2. Load prior year weekly pet days
    3. Apply growth rates to produce budget pet days and revenue
    4. Calculate labour from MPP and wage assumptions
    5. Prorate fixed costs from monthly to weekly
    6. Upsert into site_weekly_budget
    7. Roll up to site_budget_entries for model consumption
    """
    own_session = db is None
    if own_session:
        session = async_session_factory()
        db = await session.__aenter__()
    try:
        result = await _calculate_inner(db, version_id, location_id)
        # FIX(M20): only commit on success — previously finally block committed partial data
        if own_session:
            await db.commit()
        return result
    except Exception:
        if own_session:
            await db.rollback()
        raise
    finally:
        if own_session:
            await session.__aexit__(None, None, None)


async def _calculate_inner(
    db: AsyncSession,
    version_id: uuid.UUID,
    location_id: uuid.UUID,
) -> dict:
    version = await db.get(BudgetVersion, version_id)
    if version is None:
        raise ValueError(f"Budget version {version_id} not found")

    fy_year = version.fy_year
    prior_fy = fy_year - 1

    result = await db.execute(
        select(SiteBudgetAssumption).where(
            SiteBudgetAssumption.version_id == version_id,
            SiteBudgetAssumption.location_id == location_id,
        )
    )
    assumptions = result.scalar_one_or_none()
    if assumptions is None:
        assumptions = await _auto_populate_assumptions(db, version_id, location_id, fy_year, prior_fy)

    result = await db.execute(
        select(WeeklyPeriod)
        .where(WeeklyPeriod.fy_year == fy_year)
        .order_by(WeeklyPeriod.week_start_date)
    )
    budget_weeks = result.scalars().all()
    if not budget_weeks:
        raise ValueError(f"No weekly periods for FY{fy_year}")

    prior_pet_days = await _get_prior_year_pet_days(db, location_id, prior_fy)
    prior_avg_price = await _get_prior_year_avg_price(db, location_id, prior_fy)
    prior_avg_wage = await _get_prior_year_avg_wage(db, location_id, prior_fy)

    result = await db.execute(
        select(WeeklyPeriod)
        .where(WeeklyPeriod.fy_year == prior_fy)
        .order_by(WeeklyPeriod.week_start_date)
    )
    prior_weeks = result.scalars().all()
    prior_week_list = list(prior_weeks)

    price_growth = Decimal("1") + _d(assumptions.price_growth_pct)
    pd_growth = Decimal("1") + _d(assumptions.pet_day_growth_pct)
    wage_growth = Decimal("1") + _d(assumptions.wage_increase_pct)
    budget_avg_price = prior_avg_price * price_growth
    budget_avg_wage = prior_avg_wage * wage_growth
    mpp_mins = _d(assumptions.mpp_mins) or Decimal("15")
    min_daily_hours = _d(assumptions.min_daily_hours) or Decimal("8")
    cogs_pct = _d(assumptions.cogs_pct)
    advertising_pct = _d(assumptions.advertising_pct_revenue) or Decimal("0")

    monthly_costs = {
        "rent": (_d(assumptions.rent_monthly), _d(assumptions.rent_growth_pct)),
        "utilities": (_d(assumptions.utilities_monthly), _d(assumptions.utilities_growth_pct)),
        "rm": (_d(assumptions.rm_monthly), _d(assumptions.rm_growth_pct)),
        "it": (_d(assumptions.it_monthly), _d(assumptions.it_growth_pct)),
        "general": (_d(assumptions.general_monthly), _d(assumptions.general_growth_pct)),
    }

    now = datetime.now(timezone.utc)
    weeks_calculated = 0

    for i, week in enumerate(budget_weeks):
        prior_week_data = {}
        if i < len(prior_week_list):
            pw = prior_week_list[i]
            prior_week_data = prior_pet_days.get(pw.id, {s: 0 for s in SERVICE_TYPES})
        else:
            prior_week_data = {s: 0 for s in SERVICE_TYPES}

        prior_boarding = prior_week_data.get("boarding", 0)
        prior_daycare = prior_week_data.get("daycare", 0)
        prior_grooming = prior_week_data.get("grooming", 0)
        prior_wash = prior_week_data.get("wash", 0)
        prior_training = prior_week_data.get("training", 0)
        prior_total = sum(prior_week_data.values())

        prior_week_rev = Decimal(str(prior_total)) * prior_avg_price

        budget_boarding = int(math.ceil(prior_boarding * float(pd_growth)))
        budget_daycare = int(math.ceil(prior_daycare * float(pd_growth)))
        budget_grooming = int(math.ceil(prior_grooming * float(pd_growth)))
        budget_wash = int(math.ceil(prior_wash * float(pd_growth)))
        budget_training = int(math.ceil(prior_training * float(pd_growth)))
        budget_total_pd = budget_boarding + budget_daycare + budget_grooming + budget_wash + budget_training

        budget_revenue = Decimal(str(budget_total_pd)) * budget_avg_price

        labour_hours_from_pd = Decimal(str(budget_total_pd)) * mpp_mins / Decimal("60")
        labour_hours_floor = min_daily_hours * Decimal("7")
        labour_hours = max(labour_hours_from_pd, labour_hours_floor)
        budget_labour = labour_hours * budget_avg_wage

        budget_cogs = budget_revenue * cogs_pct
        budget_advertising = budget_revenue * advertising_pct

        days_in_month = Decimal(str(week.days_in_fy_month or 30))
        days_this_week = Decimal(str(week.days_this_week_in_fy_month or 7))
        proration = days_this_week / days_in_month if days_in_month else Decimal("0.25")

        week_fixed = {}
        for cost_key, (monthly_base, growth_pct) in monthly_costs.items():
            grown = monthly_base * (Decimal("1") + growth_pct)
            week_fixed[cost_key] = grown * proration

        existing = await db.execute(
            select(SiteWeeklyBudget).where(
                SiteWeeklyBudget.version_id == version_id,
                SiteWeeklyBudget.location_id == location_id,
                SiteWeeklyBudget.week_id == week.id,
            )
        )
        existing_row = existing.scalar_one_or_none()

        if existing_row and existing_row.is_overridden:
            existing_row.prior_year_pet_days_boarding = prior_boarding
            existing_row.prior_year_pet_days_daycare = prior_daycare
            existing_row.prior_year_pet_days_grooming = prior_grooming
            existing_row.prior_year_pet_days_wash = prior_wash
            existing_row.prior_year_pet_days_training = prior_training
            existing_row.prior_year_revenue = float(prior_week_rev)
            existing_row.calculated_at = now
        else:
            values = dict(
                version_id=version_id,
                location_id=location_id,
                week_id=week.id,
                prior_year_pet_days_boarding=prior_boarding,
                prior_year_pet_days_daycare=prior_daycare,
                prior_year_pet_days_grooming=prior_grooming,
                prior_year_pet_days_wash=prior_wash,
                prior_year_pet_days_training=prior_training,
                prior_year_revenue=float(prior_week_rev),
                budget_pet_days_boarding=budget_boarding,
                budget_pet_days_daycare=budget_daycare,
                budget_pet_days_grooming=budget_grooming,
                budget_pet_days_wash=budget_wash,
                budget_pet_days_training=budget_training,
                budget_revenue=float(budget_revenue),
                budget_labour=float(budget_labour),
                budget_cogs=float(budget_cogs),
                budget_rent=float(week_fixed.get("rent", 0)),
                budget_utilities=float(week_fixed.get("utilities", 0)),
                budget_rm=float(week_fixed.get("rm", 0)),
                budget_it=float(week_fixed.get("it", 0)),
                budget_general=float(week_fixed.get("general", 0)),
                budget_advertising=float(budget_advertising),
                is_overridden=False,
                calculated_at=now,
            )

            stmt = insert(SiteWeeklyBudget).values(
                id=uuid.uuid4(), **values
            ).on_conflict_do_update(
                constraint="uq_site_weekly_budget_version_loc_week",
                set_={k: v for k, v in values.items()},
            )
            await db.execute(stmt)

        weeks_calculated += 1

    await db.flush()

    await _rollup_weekly_to_site_entries(db, version_id, location_id, fy_year)

    summary = {
        "location_id": str(location_id),
        "weeks_calculated": weeks_calculated,
        "fy_year": fy_year,
        "prior_avg_price": float(prior_avg_price),
        "budget_avg_price": float(budget_avg_price),
    }
    logger.info("Site budget calculated: %s", summary)
    return summary


async def _auto_populate_assumptions(
    db: AsyncSession,
    version_id: uuid.UUID,
    location_id: uuid.UUID,
    fy_year: int,
    prior_fy: int,
) -> SiteBudgetAssumption:
    """Create assumptions from prior year actuals when not already set."""
    prior_avg_price = await _get_prior_year_avg_price(db, location_id, prior_fy)

    result = await db.execute(
        select(Period).where(Period.fy_year == prior_fy)
    )
    periods = result.scalars().all()
    period_ids = [p.id for p in periods]

    rent_monthly = Decimal("0")
    utilities_monthly = Decimal("0")

    if period_ids:
        for pattern, attr in [
            ("%rent%", "rent_monthly"),
            ("%utilit%", "utilities_monthly"),
        ]:
            result = await db.execute(
                select(func.sum(func.abs(JeLine.amount))).where(
                    JeLine.location_id == location_id,
                    JeLine.period_id.in_(period_ids),
                    JeLine.source_account_name.ilike(pattern),
                )
            )
            total = result.scalar() or 0
            monthly_avg = Decimal(str(total)) / Decimal(str(len(period_ids))) if period_ids else Decimal("0")
            if attr == "rent_monthly":
                rent_monthly = monthly_avg
            else:
                utilities_monthly = monthly_avg

    assumptions = SiteBudgetAssumption(
        version_id=version_id,
        location_id=location_id,
        fy_year=fy_year,
        price_growth_pct=Decimal("0.03"),
        pet_day_growth_pct=Decimal("0.02"),
        mpp_mins=Decimal("15"),
        min_daily_hours=Decimal("8"),
        wage_increase_pct=Decimal("0.05"),
        cogs_pct=Decimal("0.10"),
        rent_monthly=rent_monthly,
        rent_growth_pct=Decimal("0.03"),
        utilities_monthly=utilities_monthly,
        utilities_growth_pct=Decimal("0.03"),
        rm_growth_pct=Decimal("0.05"),
        it_growth_pct=Decimal("0.05"),
        general_growth_pct=Decimal("0.05"),
    )
    db.add(assumptions)
    await db.flush()
    return assumptions


async def _rollup_weekly_to_site_entries(
    db: AsyncSession,
    version_id: uuid.UUID,
    location_id: uuid.UUID,
    fy_year: int,
) -> None:
    """Sum weekly budget rows into site_budget_entries for the model engine."""
    result = await db.execute(
        select(SiteWeeklyBudget).where(
            SiteWeeklyBudget.version_id == version_id,
            SiteWeeklyBudget.location_id == location_id,
        )
    )
    weekly_rows = result.scalars().all()

    line_item_map = {
        "boarding_revenue": lambda r: float(r.override_revenue if r.is_overridden and r.override_revenue else r.budget_revenue or 0),
        "direct_wages": lambda r: float(r.override_labour if r.is_overridden and r.override_labour else r.budget_labour or 0),
        "direct_costs": lambda r: float(r.budget_cogs or 0),
        "rent": lambda r: float(r.budget_rent or 0),
        "utilities": lambda r: float(r.budget_utilities or 0),
        "repairs_maintenance": lambda r: float(r.budget_rm or 0),
        "it_systems": lambda r: float(r.budget_it or 0),
        "general_admin": lambda r: float(r.budget_general or 0),
        "advertising": lambda r: float(r.budget_advertising or 0),
    }

    for line_item, extract_fn in line_item_map.items():
        for row in weekly_rows:
            amount = extract_fn(row)
            stmt = insert(SiteBudgetEntry).values(
                id=uuid.uuid4(),
                version_id=version_id,
                location_id=location_id,
                model_line_item=line_item,
                week_id=row.week_id,
                amount=amount,
                driver_type="manual",
                updated_at=datetime.now(timezone.utc),
            ).on_conflict_do_update(
                constraint="uq_site_budget_entries_version_loc_week_line",
                set_={
                    "amount": amount,
                    "updated_at": datetime.now(timezone.utc),
                },
            )
            try:
                await db.execute(stmt)
            except Exception:
                result2 = await db.execute(
                    select(SiteBudgetEntry).where(
                        SiteBudgetEntry.version_id == version_id,
                        SiteBudgetEntry.location_id == location_id,
                        SiteBudgetEntry.week_id == row.week_id,
                        SiteBudgetEntry.model_line_item == line_item,
                    )
                )
                existing = result2.scalar_one_or_none()
                if existing:
                    existing.amount = amount
                    existing.updated_at = datetime.now(timezone.utc)
                else:
                    db.add(SiteBudgetEntry(
                        version_id=version_id,
                        location_id=location_id,
                        model_line_item=line_item,
                        week_id=row.week_id,
                        amount=amount,
                        driver_type="manual",
                        updated_at=datetime.now(timezone.utc),
                    ))

    await db.flush()


async def calculate_all_sites(version_id: uuid.UUID) -> dict:
    """Run budget calculation for all active locations."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(Location).where(Location.is_active.is_(True))
        )
        locations = result.scalars().all()

        results = {}
        errors = []
        for loc in locations:
            try:
                r = await _calculate_inner(db, version_id, loc.id)
                results[str(loc.id)] = r
            except Exception as exc:
                logger.exception("Budget calc failed for %s", loc.name)
                errors.append({"location": loc.name, "error": str(exc)})

        await db.commit()

        from app.services.site_rollup_service import rollup_sites_to_entity

        async with async_session_factory() as db2:
            rollup = await rollup_sites_to_entity(db2, version_id)
            await db2.commit()

    return {
        "sites_calculated": len(results),
        "errors": errors,
        "rollup": rollup,
    }
