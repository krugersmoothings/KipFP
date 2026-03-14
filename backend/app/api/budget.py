"""Budget model API — trigger calculation, check status, read outputs."""

from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import datetime, timezone

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_finance
from app.db.models.account import Account, AccountType, Statement
from app.db.models.budget import BudgetVersion, ModelAssumption, ModelOutput
from app.db.models.debt import DebtFacility, DebtSchedule
from app.db.models.entity import Entity
from app.db.models.location import Location, SiteBudgetEntry
from app.db.models.period import Period, WeeklyPeriod
from app.db.models.user import User
from app.db.models.wc import WcDriver
from app.schemas.budget import (
    AssumptionPayload,
    BudgetVersionCreate,
    BudgetVersionRead,
    CalculationStatusResponse,
    CalculationTriggerResponse,
    DebtFacilityRead,
    DebtFacilityUpdate,
    DebtScheduleRowRead,
    ModelAssumptionRead,
    ModelOutputResponse,
    ModelOutputRow,
    SiteBudgetGridRead,
    SiteBudgetLineRead,
    SiteBudgetSavePayload,
    SiteRollupRow,
    SiteSummaryRead,
    WcDriverRead,
    WcDriverUpdate,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])

MONTH_ABBR = [
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
]


def _period_label(period: Period) -> str:
    if period.period_start:
        return period.period_start.strftime("%b-%y")
    cal_year = period.fy_year - 1 if period.fy_month <= 6 else period.fy_year
    return f"{MONTH_ABBR[period.fy_month - 1]}-{cal_year % 100:02d}"


# ── Section header config ────────────────────────────────────────────────────

IS_SECTIONS: dict[str, list[AccountType]] = {
    "Revenue": [AccountType.income, AccountType.cogs],
    "Operating Expenses": [AccountType.opex],
    "Depreciation & Amortisation": [AccountType.depreciation],
    "Interest": [AccountType.interest],
    "Tax": [AccountType.tax],
}

BS_SECTIONS: dict[str, list[AccountType]] = {
    "Assets": [AccountType.asset],
    "Liabilities": [AccountType.liability],
    "Equity": [AccountType.equity],
}

CF_SECTIONS: dict[str, list[str]] = {
    "Operating Activities": ["CF-OPERATING"],
    "Investing Activities": ["CF-INVESTING"],
    "Financing Activities": ["CF-FINANCING"],
    "Net Cash Flow": ["CF-NET"],
}


# ── GET /budgets ──────────────────────────────────────────────────────────────


@router.get("/", response_model=list[BudgetVersionRead])
async def list_budget_versions(
    fy_year: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    q = select(BudgetVersion).order_by(BudgetVersion.created_at.desc())
    if fy_year is not None:
        q = q.where(BudgetVersion.fy_year == fy_year)
    result = await db.execute(q)
    return list(result.scalars().all())


# ── POST /budgets ─────────────────────────────────────────────────────────────


@router.post("/", response_model=BudgetVersionRead, status_code=status.HTTP_201_CREATED)
async def create_budget_version(
    payload: BudgetVersionCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    version = BudgetVersion(
        name=payload.name,
        fy_year=payload.fy_year,
        version_type=payload.version_type,
        base_version_id=payload.base_version_id,
        created_by=user.id,
    )
    db.add(version)
    await db.commit()
    await db.refresh(version)
    return version


# ── GET /budgets/{id}/assumptions ─────────────────────────────────────────────


@router.get("/{budget_id}/assumptions", response_model=list[ModelAssumptionRead])
async def get_assumptions(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    result = await db.execute(
        select(ModelAssumption).where(
            ModelAssumption.budget_version_id == budget_id
        )
    )
    return list(result.scalars().all())


# ── PUT /budgets/{id}/assumptions ─────────────────────────────────────────────


@router.put("/{budget_id}/assumptions", response_model=list[ModelAssumptionRead])
async def save_assumptions(
    budget_id: uuid.UUID,
    assumptions: list[AssumptionPayload],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    for payload in assumptions:
        result = await db.execute(
            select(ModelAssumption).where(
                ModelAssumption.budget_version_id == budget_id,
                ModelAssumption.entity_id == payload.entity_id,
                ModelAssumption.assumption_key == payload.assumption_key,
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            existing.assumption_value = payload.assumption_value
            existing.updated_by = user.id
            existing.updated_at = datetime.now(timezone.utc)
        else:
            db.add(ModelAssumption(
                budget_version_id=budget_id,
                entity_id=payload.entity_id,
                assumption_key=payload.assumption_key,
                assumption_value=payload.assumption_value,
                updated_by=user.id,
            ))

    await db.commit()

    result = await db.execute(
        select(ModelAssumption).where(
            ModelAssumption.budget_version_id == budget_id
        )
    )
    return list(result.scalars().all())


# ── GET /budgets/{id}/wc-drivers ──────────────────────────────────────────────


@router.get("/{budget_id}/wc-drivers", response_model=list[WcDriverRead])
async def get_wc_drivers(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    result = await db.execute(
        select(WcDriver).where(WcDriver.budget_version_id == budget_id)
    )
    drivers = list(result.scalars().all())

    account_ids = {d.account_id for d in drivers}
    acct_result = await db.execute(
        select(Account).where(Account.id.in_(account_ids))
    ) if account_ids else None
    acct_map = {a.id: a.name for a in acct_result.scalars().all()} if acct_result else {}

    return [
        WcDriverRead(
            id=d.id,
            entity_id=d.entity_id,
            account_id=d.account_id,
            account_label=acct_map.get(d.account_id, ""),
            driver_type=d.driver_type.value if d.driver_type else None,
            base_days=float(d.base_days) if d.base_days is not None else None,
            seasonal_factors=d.seasonal_factors,
            notes=d.notes,
        )
        for d in drivers
    ]


# ── PUT /budgets/{id}/wc-drivers ──────────────────────────────────────────────


@router.put("/{budget_id}/wc-drivers", response_model=list[WcDriverRead])
async def update_wc_drivers(
    budget_id: uuid.UUID,
    updates: list[WcDriverUpdate],
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    for upd in updates:
        driver = await db.get(WcDriver, upd.id)
        if driver and driver.budget_version_id == budget_id:
            driver.base_days = upd.base_days
            driver.seasonal_factors = upd.seasonal_factors
            driver.last_updated_by = user.id
            driver.last_updated_at = datetime.now(timezone.utc)

    await db.commit()
    return await get_wc_drivers(budget_id, db, user)


# ── GET /budgets/{id}/debt ────────────────────────────────────────────────────


@router.get("/{budget_id}/debt", response_model=list[DebtFacilityRead])
async def get_debt_facilities(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    fac_result = await db.execute(
        select(DebtFacility)
        .where(DebtFacility.is_active.is_(True))
        .order_by(DebtFacility.sort_order)
    )
    facilities = list(fac_result.scalars().all())

    period_result = await db.execute(
        select(Period)
        .where(Period.fy_year == version.fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(period_result.scalars().all())
    period_ids = [p.id for p in periods]

    sched_result = await db.execute(
        select(DebtSchedule).where(
            DebtSchedule.budget_version_id == budget_id,
            DebtSchedule.period_id.in_(period_ids),
        )
    ) if period_ids else None
    schedules = list(sched_result.scalars().all()) if sched_result else []

    sched_by_fac: dict[uuid.UUID, list] = defaultdict(list)
    for s in schedules:
        sched_by_fac[s.facility_id].append(s)

    period_label_map = {p.id: _period_label(p) for p in periods}

    result = []
    for fac in facilities:
        fac_schedules = sorted(
            sched_by_fac.get(fac.id, []),
            key=lambda s: period_ids.index(s.period_id) if s.period_id in period_ids else 999,
        )
        schedule_rows = [
            DebtScheduleRowRead(
                period_label=period_label_map.get(s.period_id, ""),
                opening_balance=float(s.opening_balance or 0),
                drawdown=float(s.drawdown or 0),
                repayment=float(s.repayment or 0),
                closing_balance=float(s.closing_balance or 0),
                interest_expense=float(s.interest_expense or 0),
                interest_rate_applied=float(s.interest_rate_applied or 0),
            )
            for s in fac_schedules
        ]
        result.append(DebtFacilityRead(
            id=fac.id,
            code=fac.code,
            name=fac.name,
            entity_id=fac.entity_id,
            facility_type=fac.facility_type.value if fac.facility_type else None,
            opening_balance=float(fac.opening_balance),
            base_rate=float(fac.base_rate) if fac.base_rate is not None else None,
            margin=float(fac.margin),
            amort_type=fac.amort_type.value if fac.amort_type else None,
            monthly_repayment=float(fac.monthly_repayment) if fac.monthly_repayment is not None else None,
            maturity_date=str(fac.maturity_date) if fac.maturity_date else None,
            is_active=fac.is_active,
            schedule=schedule_rows,
        ))

    return result


# ── PUT /budgets/{id}/debt/facilities/{fid} ──────────────────────────────────


@router.put("/{budget_id}/debt/facilities/{facility_id}", response_model=DebtFacilityRead)
async def update_debt_facility(
    budget_id: uuid.UUID,
    facility_id: uuid.UUID,
    payload: DebtFacilityUpdate,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    facility = await db.get(DebtFacility, facility_id)
    if facility is None:
        raise HTTPException(status_code=404, detail="Facility not found")

    facility.base_rate = payload.base_rate
    facility.margin = payload.margin
    facility.monthly_repayment = payload.monthly_repayment
    await db.commit()
    await db.refresh(facility)

    return DebtFacilityRead(
        id=facility.id,
        code=facility.code,
        name=facility.name,
        entity_id=facility.entity_id,
        facility_type=facility.facility_type.value if facility.facility_type else None,
        opening_balance=float(facility.opening_balance),
        base_rate=float(facility.base_rate) if facility.base_rate is not None else None,
        margin=float(facility.margin),
        amort_type=facility.amort_type.value if facility.amort_type else None,
        monthly_repayment=float(facility.monthly_repayment) if facility.monthly_repayment is not None else None,
        maturity_date=str(facility.maturity_date) if facility.maturity_date else None,
        is_active=facility.is_active,
        schedule=[],
    )


# ── GET /budgets/{id}/sites ───────────────────────────────────────────────────


@router.get("/{budget_id}/sites", response_model=list[SiteSummaryRead])
async def list_sites(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    result = await db.execute(
        select(Location)
        .where(Location.is_active.is_(True))
        .order_by(Location.state, Location.name)
    )
    locations = list(result.scalars().all())

    # Load periods for labels
    period_result = await db.execute(
        select(Period)
        .where(Period.fy_year == version.fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(period_result.scalars().all())
    period_labels = {p.fy_month: _period_label(p) for p in periods}

    # Load weekly periods for proration
    wp_result = await db.execute(
        select(WeeklyPeriod).where(WeeklyPeriod.fy_year == version.fy_year)
    )
    weekly_periods = list(wp_result.scalars().all())
    week_to_month: dict[uuid.UUID, int] = {}
    week_proration: dict[uuid.UUID, float] = {}
    for wp in weekly_periods:
        if wp.fy_month is not None and wp.days_this_week_in_fy_month is not None:
            week_to_month[wp.id] = wp.fy_month
            week_proration[wp.id] = wp.days_this_week_in_fy_month / 7.0

    # Load all site budget entries for this version
    entry_result = await db.execute(
        select(SiteBudgetEntry).where(SiteBudgetEntry.version_id == budget_id)
    )
    entries = list(entry_result.scalars().all())

    # Aggregate revenue per site per month
    site_month_totals: dict[uuid.UUID, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    revenue_lines = {"boarding_revenue", "grooming_revenue", "other_revenue"}
    for entry in entries:
        if entry.model_line_item not in revenue_lines:
            continue
        if entry.week_id and entry.week_id in week_to_month:
            fy_month = week_to_month[entry.week_id]
            factor = week_proration.get(entry.week_id, 1.0)
            amount = float(entry.amount or 0) * factor
        else:
            continue
        label = period_labels.get(fy_month, f"M{fy_month:02d}")
        site_month_totals[entry.location_id][label] += amount

    return [
        SiteSummaryRead(
            location_id=loc.id,
            code=loc.code or "",
            name=loc.name or "",
            state=loc.state,
            entity_id=loc.entity_id,
            capacity_dogs=loc.capacity_dogs,
            monthly_totals=dict(site_month_totals.get(loc.id, {})),
        )
        for loc in locations
    ]


# ── GET /budgets/{id}/sites/{location_id} ────────────────────────────────────

SITE_LINE_ITEMS = [
    "boarding_revenue",
    "grooming_revenue",
    "other_revenue",
    "direct_wages",
    "direct_costs",
    "rent",
]

SITE_LINE_LABELS = {
    "boarding_revenue": "Boarding Revenue",
    "grooming_revenue": "Grooming Revenue",
    "other_revenue": "Other Revenue",
    "direct_wages": "Direct Wages",
    "direct_costs": "Direct Costs",
    "rent": "Rent",
}


@router.get("/{budget_id}/sites/{location_id}", response_model=SiteBudgetGridRead)
async def get_site_budget(
    budget_id: uuid.UUID,
    location_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    location = await db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    # Load periods
    period_result = await db.execute(
        select(Period)
        .where(Period.fy_year == version.fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(period_result.scalars().all())
    period_labels = [_period_label(p) for p in periods]
    month_label_map = {p.fy_month: _period_label(p) for p in periods}

    # Load weekly periods for this FY
    wp_result = await db.execute(
        select(WeeklyPeriod).where(WeeklyPeriod.fy_year == version.fy_year)
    )
    weekly_periods = list(wp_result.scalars().all())
    week_to_month: dict[uuid.UUID, int] = {}
    week_proration: dict[uuid.UUID, float] = {}
    for wp in weekly_periods:
        if wp.fy_month is not None and wp.days_this_week_in_fy_month is not None:
            week_to_month[wp.id] = wp.fy_month
            week_proration[wp.id] = wp.days_this_week_in_fy_month / 7.0

    # Load entries for this location
    entry_result = await db.execute(
        select(SiteBudgetEntry).where(
            SiteBudgetEntry.version_id == budget_id,
            SiteBudgetEntry.location_id == location_id,
        )
    )
    entries = list(entry_result.scalars().all())

    # Build line → month → amount (prorated from weekly)
    line_values: dict[str, dict[str, float]] = {
        li: {} for li in SITE_LINE_ITEMS
    }
    for entry in entries:
        li = entry.model_line_item
        if li not in line_values:
            continue
        if entry.week_id and entry.week_id in week_to_month:
            fy_month = week_to_month[entry.week_id]
            factor = week_proration.get(entry.week_id, 1.0)
            amount = float(entry.amount or 0) * factor
            label = month_label_map.get(fy_month, f"M{fy_month:02d}")
            line_values[li][label] = line_values[li].get(label, 0.0) + amount

    lines = [
        SiteBudgetLineRead(
            line_item=SITE_LINE_LABELS.get(li, li),
            values=line_values.get(li, {}),
        )
        for li in SITE_LINE_ITEMS
    ]

    return SiteBudgetGridRead(
        location_id=location_id,
        location_name=location.name or "",
        periods=period_labels,
        lines=lines,
    )


# ── PUT /budgets/{id}/sites/{location_id} ────────────────────────────────────


@router.put("/{budget_id}/sites/{location_id}", response_model=SiteBudgetGridRead)
async def save_site_budget(
    budget_id: uuid.UUID,
    location_id: uuid.UUID,
    payload: SiteBudgetSavePayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    location = await db.get(Location, location_id)
    if location is None:
        raise HTTPException(status_code=404, detail="Location not found")

    # Load periods + weekly periods
    period_result = await db.execute(
        select(Period)
        .where(Period.fy_year == version.fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(period_result.scalars().all())
    label_to_month: dict[str, int] = {_period_label(p): p.fy_month for p in periods}

    wp_result = await db.execute(
        select(WeeklyPeriod)
        .where(WeeklyPeriod.fy_year == version.fy_year)
        .order_by(WeeklyPeriod.week_start_date)
    )
    weekly_periods = list(wp_result.scalars().all())

    # Group weekly periods by fy_month — pick the first week of each month
    # to store the monthly total (driver_type='manual')
    first_week_per_month: dict[int, WeeklyPeriod] = {}
    for wp in weekly_periods:
        if wp.fy_month is not None and wp.fy_month not in first_week_per_month:
            first_week_per_month[wp.fy_month] = wp

    now = datetime.now(timezone.utc)
    label_to_line = {v: k for k, v in SITE_LINE_LABELS.items()}

    # Delete existing entries for this version + location
    from sqlalchemy import delete
    await db.execute(
        delete(SiteBudgetEntry).where(
            SiteBudgetEntry.version_id == budget_id,
            SiteBudgetEntry.location_id == location_id,
        )
    )

    # Insert new entries — one per line_item per month
    for line in payload.lines:
        line_item = label_to_line.get(line.line_item, line.line_item)
        for label, amount in line.values.items():
            fy_month = label_to_month.get(label)
            if fy_month is None:
                continue
            week = first_week_per_month.get(fy_month)
            if week is None:
                continue
            db.add(SiteBudgetEntry(
                version_id=budget_id,
                location_id=location_id,
                model_line_item=line_item,
                week_id=week.id,
                amount=amount,
                driver_type="manual",
                entered_by=user.id,
                updated_at=now,
            ))

    await db.commit()

    # Trigger rollup in background
    from app.services.site_rollup_service import rollup_sites_to_entity
    try:
        await rollup_sites_to_entity(db, budget_id)
        await db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception("Rollup failed after site save")

    return await get_site_budget(budget_id, location_id, db, user)


# ── GET /budgets/{id}/sites/rollup ───────────────────────────────────────────


@router.get("/{budget_id}/site-rollup", response_model=list[SiteRollupRow])
async def get_site_rollup(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    # Load periods
    period_result = await db.execute(
        select(Period)
        .where(Period.fy_year == version.fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(period_result.scalars().all())
    month_label: dict[int, str] = {p.fy_month: _period_label(p) for p in periods}

    # Load weekly periods for proration
    wp_result = await db.execute(
        select(WeeklyPeriod).where(WeeklyPeriod.fy_year == version.fy_year)
    )
    weekly_periods = list(wp_result.scalars().all())
    week_to_month: dict[uuid.UUID, int] = {}
    week_proration: dict[uuid.UUID, float] = {}
    for wp in weekly_periods:
        if wp.fy_month is not None and wp.days_this_week_in_fy_month is not None:
            week_to_month[wp.id] = wp.fy_month
            week_proration[wp.id] = wp.days_this_week_in_fy_month / 7.0

    # Load locations → entity mapping
    loc_result = await db.execute(select(Location).where(Location.is_active.is_(True)))
    locations = list(loc_result.scalars().all())
    loc_entity: dict[uuid.UUID, uuid.UUID] = {
        loc.id: loc.entity_id for loc in locations if loc.entity_id
    }

    # Load entities
    ent_result = await db.execute(
        select(Entity).where(Entity.is_active.is_(True))
    )
    entity_map = {e.id: e for e in ent_result.scalars().all()}

    # Load site entries
    entry_result = await db.execute(
        select(SiteBudgetEntry).where(SiteBudgetEntry.version_id == budget_id)
    )
    entries = list(entry_result.scalars().all())

    # Aggregate by entity × line_item × month
    agg: dict[tuple[uuid.UUID, str], dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    for entry in entries:
        entity_id = loc_entity.get(entry.location_id)
        if entity_id is None:
            continue
        if entry.week_id and entry.week_id in week_to_month:
            fy_month = week_to_month[entry.week_id]
            factor = week_proration.get(entry.week_id, 1.0)
            amount = float(entry.amount or 0) * factor
        else:
            continue
        label = month_label.get(fy_month, f"M{fy_month:02d}")
        agg[(entity_id, entry.model_line_item or "")][label] += amount

    # Load model assumptions for comparison
    ma_result = await db.execute(
        select(ModelAssumption).where(
            ModelAssumption.budget_version_id == budget_id
        )
    )
    model_assumptions = list(ma_result.scalars().all())
    ma_map: dict[tuple[uuid.UUID | None, str], dict] = {}
    for ma in model_assumptions:
        ma_map[(ma.entity_id, ma.assumption_key)] = ma.assumption_value

    rows: list[SiteRollupRow] = []
    for (entity_id, line_item), site_totals in sorted(
        agg.items(), key=lambda x: (str(x[0][0]), x[0][1])
    ):
        entity = entity_map.get(entity_id)
        if not entity:
            continue

        assumption_key = f"site_rollup.{line_item}"
        model_vals = ma_map.get((entity_id, assumption_key), {})

        variance: dict[str, float] = {}
        for lbl in site_totals:
            sv = site_totals.get(lbl, 0.0)
            mv = float(model_vals.get(lbl, 0.0)) if isinstance(model_vals, dict) else 0.0
            variance[lbl] = sv - mv

        rows.append(SiteRollupRow(
            entity_code=entity.code or "",
            entity_name=entity.name,
            line_item=SITE_LINE_LABELS.get(line_item, line_item),
            site_total=dict(site_totals),
            model_assumption={
                k: float(v)
                for k, v in model_vals.items()
                if isinstance(v, (int, float))
            } if isinstance(model_vals, dict) else {},
            variance=variance,
        ))

    return rows


# ── POST /budgets/{id}/calculate ─────────────────────────────────────────────


@router.post(
    "/{budget_id}/calculate",
    response_model=CalculationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_calculation(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    from app.worker import run_model_task

    task_id = f"model-{budget_id}"
    run_model_task.apply_async(args=[str(budget_id)], task_id=task_id)
    return CalculationTriggerResponse(task_id=task_id, status="queued")


# ── GET /budgets/{id}/status ─────────────────────────────────────────────────


@router.get("/{budget_id}/status", response_model=CalculationStatusResponse)
async def get_calculation_status(
    budget_id: uuid.UUID,
    _user: User = Depends(require_finance),
):
    from app.worker import celery_app

    # Find the most recent task for this budget version.
    # In a production system you'd track task_id on the version row;
    # for now inspect via Celery backend.
    task_key = f"model-{budget_id}"
    result = AsyncResult(task_key, app=celery_app)

    if result.state == "PENDING":
        return CalculationStatusResponse(
            task_id=task_key, status="no_task_found"
        )

    return CalculationStatusResponse(
        task_id=task_key,
        status=result.state.lower(),
        result=result.result if result.successful() else None,
    )


# ── GET /budgets/{id}/output/is ──────────────────────────────────────────────


@router.get("/{budget_id}/output/is", response_model=ModelOutputResponse)
async def get_budget_is(
    budget_id: uuid.UUID,
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    return await _get_model_output(db, budget_id, Statement.is_, fy_month)


@router.get("/{budget_id}/output/bs", response_model=ModelOutputResponse)
async def get_budget_bs(
    budget_id: uuid.UUID,
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    return await _get_model_output(db, budget_id, Statement.bs, fy_month)


@router.get("/{budget_id}/output/cf", response_model=ModelOutputResponse)
async def get_budget_cf(
    budget_id: uuid.UUID,
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    return await _get_model_output(db, budget_id, Statement.cf, fy_month)


# ── Shared output renderer ──────────────────────────────────────────────────


async def _get_model_output(
    db: AsyncSession,
    budget_id: uuid.UUID,
    statement: Statement,
    fy_month: int | None,
) -> ModelOutputResponse:
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    fy_year = version.fy_year

    # Resolve periods
    if fy_month is not None:
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month <= fy_month)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        target = next((p for p in all_periods if p.fy_month == fy_month), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Period not found")
        period_ids = [p.id for p in all_periods]
        target_label = _period_label(target)
        column_labels = [target_label, "YTD"]
        period_id_to_label = {p.id: _period_label(p) for p in all_periods}
    else:
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        if not all_periods:
            raise HTTPException(status_code=404, detail="No periods for this FY")
        period_ids = [p.id for p in all_periods]
        column_labels = [_period_label(p) for p in all_periods]
        period_id_to_label = {p.id: _period_label(p) for p in all_periods}

    # Load accounts for the statement (or CF pseudo-accounts)
    is_cf = statement == Statement.cf
    if is_cf:
        cf_codes = ["CF-OPERATING", "CF-INVESTING", "CF-FINANCING", "CF-NET"]
        result = await db.execute(
            select(Account).where(Account.code.in_(cf_codes))
        )
        accounts = list(result.scalars().all())
        if not accounts:
            accounts = _build_cf_pseudo_accounts(cf_codes)
    else:
        result = await db.execute(
            select(Account)
            .where(Account.statement == statement)
            .order_by(Account.sort_order)
        )
        accounts = list(result.scalars().all())

    account_ids = [a.id for a in accounts]

    # Load model outputs
    result = await db.execute(
        select(ModelOutput).where(
            ModelOutput.version_id == budget_id,
            ModelOutput.period_id.in_(period_ids),
            ModelOutput.account_id.in_(account_ids),
        )
    )
    model_outputs = result.scalars().all()

    # Load entities
    result = await db.execute(select(Entity))
    entities_map = {e.id: e for e in result.scalars().all()}

    # Index outputs
    group_totals: dict[uuid.UUID, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    entity_amounts: dict[uuid.UUID, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )

    for mo in model_outputs:
        label = period_id_to_label.get(mo.period_id)
        if label is None:
            continue
        if mo.entity_id is None:
            group_totals[mo.account_id][label] += float(mo.amount)
        else:
            ent = entities_map.get(mo.entity_id)
            ecode = ent.code if ent else "?"
            entity_amounts[mo.account_id][ecode][label] += float(mo.amount)

    # Build rows with section headers
    rows: list[ModelOutputRow] = []

    if is_cf:
        for section, codes in CF_SECTIONS.items():
            rows.append(ModelOutputRow(
                account_code="",
                label=section,
                is_section_header=True,
            ))
            for acct in accounts:
                if acct.code not in codes:
                    continue
                vals = _build_values(
                    acct, group_totals, column_labels, fy_month, period_id_to_label
                )
                eb = _build_entity_breakdown(
                    acct, entity_amounts, column_labels, fy_month, period_id_to_label
                )
                rows.append(ModelOutputRow(
                    account_code=acct.code,
                    label=acct.name,
                    is_subtotal=getattr(acct, "is_subtotal", False),
                    indent_level=0 if getattr(acct, "is_subtotal", False) else 1,
                    values=vals,
                    entity_breakdown=eb,
                ))
    else:
        sections = BS_SECTIONS if statement == Statement.bs else IS_SECTIONS
        type_to_section: dict[AccountType, str] = {}
        for sec, types in sections.items():
            for t in types:
                type_to_section[t] = sec

        seen_sections: set[str] = set()
        for acct in accounts:
            sec = type_to_section.get(acct.account_type)
            if sec and sec not in seen_sections:
                seen_sections.add(sec)
                rows.append(ModelOutputRow(
                    account_code="",
                    label=sec,
                    is_section_header=True,
                ))

            vals = _build_values(
                acct, group_totals, column_labels, fy_month, period_id_to_label
            )
            eb = _build_entity_breakdown(
                acct, entity_amounts, column_labels, fy_month, period_id_to_label
            )
            rows.append(ModelOutputRow(
                account_code=acct.code,
                label=acct.name,
                is_subtotal=acct.is_subtotal,
                indent_level=0 if acct.is_subtotal else 1,
                values=vals,
                entity_breakdown=eb,
            ))

    return ModelOutputResponse(
        version_id=budget_id,
        fy_year=fy_year,
        statement=statement.value,
        periods=column_labels,
        rows=rows,
    )


def _build_values(
    acct: Account,
    group_totals: dict,
    column_labels: list[str],
    fy_month: int | None,
    period_id_to_label: dict,
) -> dict[str, float]:
    month_totals = group_totals.get(acct.id, {})
    if fy_month is not None:
        target_label = column_labels[0]
        month_val = month_totals.get(target_label, 0.0)
        ytd_sum = sum(month_totals.values())
        return {target_label: month_val, "YTD": ytd_sum}
    return {lbl: month_totals.get(lbl, 0.0) for lbl in column_labels}


def _build_entity_breakdown(
    acct: Account,
    entity_amounts: dict,
    column_labels: list[str],
    fy_month: int | None,
    period_id_to_label: dict,
) -> dict[str, dict[str, float]]:
    eb: dict[str, dict[str, float]] = {}
    for ecode, period_map in entity_amounts.get(acct.id, {}).items():
        if fy_month is not None:
            target_label = column_labels[0]
            eb[ecode] = {
                target_label: period_map.get(target_label, 0.0),
                "YTD": sum(period_map.values()),
            }
        else:
            eb[ecode] = {lbl: period_map.get(lbl, 0.0) for lbl in column_labels}
    return eb


def _build_cf_pseudo_accounts(codes: list[str]) -> list:
    """If CF accounts don't exist in the DB yet, create lightweight objects."""
    from types import SimpleNamespace

    labels = {
        "CF-OPERATING": "Operating Cash Flow",
        "CF-INVESTING": "Investing Cash Flow",
        "CF-FINANCING": "Financing Cash Flow",
        "CF-NET": "Net Cash Flow",
    }
    return [
        SimpleNamespace(
            id=uuid.uuid5(uuid.NAMESPACE_DNS, c),
            code=c,
            name=labels.get(c, c),
            is_subtotal=(c == "CF-NET"),
            account_type=None,
        )
        for c in codes
    ]
