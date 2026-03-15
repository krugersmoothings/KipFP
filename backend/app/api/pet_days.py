import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, require_finance
from app.db.models.location import Location, PropertyMapping
from app.db.models.period import WeeklyPeriod
from app.db.models.pet_days import ServiceType, SitePetDay
from app.db.models.sync import SyncRun, SyncStatus, SyncTrigger
from app.db.models.user import User
from app.schemas.pet_days import (
    BigQuerySyncRequest,
    ForwardBookingWeek,
    PetDayActual,
    PetDaySiteSummary,
    PetDayWeekly,
    PropertyMappingRead,
)
from app.schemas.sync import SyncTriggerResponse

router = APIRouter(prefix="/pet-days", tags=["pet-days"])


@router.post(
    "/sync/bigquery",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_bigquery_sync(
    body: BigQuerySyncRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Manually trigger a BigQuery pet days sync for a date range."""
    from app.worker import sync_bigquery_task

    run_id = uuid.uuid4()
    run = SyncRun(
        id=run_id,
        entity_id=None,
        source_system="bigquery",
        status=SyncStatus.running,
        triggered_by=SyncTrigger.manual,
    )
    db.add(run)
    await db.commit()

    sync_bigquery_task.delay(body.date_from, body.date_to, str(run_id))
    return SyncTriggerResponse(sync_run_id=run_id, status="queued")


@router.get("/actuals", response_model=list[PetDayActual])
async def get_pet_day_actuals(
    location_id: uuid.UUID = Query(...),
    # FIX(L29): parse strings to proper date objects for type-safe comparison
    date_from: date = Query(..., alias="from"),
    date_to: date = Query(..., alias="to"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Daily pet-day actuals for a single location."""
    result = await db.execute(
        select(SitePetDay)
        .where(
            SitePetDay.location_id == location_id,
            SitePetDay.date >= date_from,
            SitePetDay.date <= date_to,
        )
        .order_by(SitePetDay.date, SitePetDay.service_type)
    )
    rows = result.scalars().all()
    return [
        PetDayActual(
            date=r.date,
            service_type=r.service_type.value,
            pet_days=r.pet_days,
            revenue_aud=float(r.revenue_aud) if r.revenue_aud else None,
        )
        for r in rows
    ]


@router.get("/weekly", response_model=list[PetDayWeekly])
async def get_pet_day_weekly(
    location_id: uuid.UUID = Query(...),
    fy_year: int = Query(...),
    fy_month: int | None = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Weekly aggregated pet-day data for a location, for a FY (and optional month)."""
    wp_query = select(WeeklyPeriod).where(WeeklyPeriod.fy_year == fy_year)
    if fy_month is not None:
        wp_query = wp_query.where(WeeklyPeriod.fy_month == fy_month)
    wp_query = wp_query.order_by(WeeklyPeriod.week_start_date)

    result = await db.execute(wp_query)
    weeks = result.scalars().all()
    if not weeks:
        return []

    date_min = weeks[0].week_start_date
    date_max = weeks[-1].week_end_date or weeks[-1].week_start_date

    result = await db.execute(
        select(SitePetDay)
        .where(
            SitePetDay.location_id == location_id,
            SitePetDay.date >= date_min,
            SitePetDay.date <= date_max,
        )
    )
    pet_days = result.scalars().all()

    week_data: dict[uuid.UUID, dict] = {}
    for w in weeks:
        week_data[w.id] = {
            "week_start": w.week_start_date,
            "week_end": w.week_end_date or w.week_start_date,
            "week_label": w.week_label,
            "boarding": 0, "daycare": 0, "grooming": 0,
            "wash": 0, "training": 0,
            "total_pet_days": 0, "total_revenue": 0.0,
        }

    for pd in pet_days:
        for w in weeks:
            end = w.week_end_date or w.week_start_date
            if w.week_start_date <= pd.date <= end:
                wd = week_data[w.id]
                svc = pd.service_type.value
                if svc in wd:
                    wd[svc] += pd.pet_days
                wd["total_pet_days"] += pd.pet_days
                wd["total_revenue"] += float(pd.revenue_aud or 0)
                break

    return [PetDayWeekly(**wd) for wd in week_data.values()]


@router.get("/summary", response_model=list[PetDaySiteSummary])
async def get_pet_day_summary(
    fy_year: int = Query(...),
    fy_month: int | None = Query(None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """All-locations pet-day summary for a FY period."""
    wp_query = select(WeeklyPeriod).where(WeeklyPeriod.fy_year == fy_year)
    if fy_month is not None:
        wp_query = wp_query.where(WeeklyPeriod.fy_month == fy_month)

    result = await db.execute(wp_query)
    weeks = result.scalars().all()
    if not weeks:
        return []

    date_min = min(w.week_start_date for w in weeks)
    date_max = max(w.week_end_date or w.week_start_date for w in weeks)

    result = await db.execute(
        select(SitePetDay)
        .where(SitePetDay.date >= date_min, SitePetDay.date <= date_max)
    )
    pet_days = result.scalars().all()

    result = await db.execute(
        select(Location).where(Location.is_active.is_(True))
    )
    locations = {loc.id: loc.name for loc in result.scalars().all()}

    by_loc: dict[uuid.UUID, dict] = defaultdict(lambda: {
        "total_boarding": 0, "total_daycare": 0, "total_grooming": 0,
        "total_wash": 0, "total_training": 0,
        "total_pet_days": 0, "total_revenue": 0.0,
    })

    for pd in pet_days:
        d = by_loc[pd.location_id]
        svc = pd.service_type.value
        key = f"total_{svc}"
        if key in d:
            d[key] += pd.pet_days
        d["total_pet_days"] += pd.pet_days
        d["total_revenue"] += float(pd.revenue_aud or 0)

    return [
        PetDaySiteSummary(
            location_id=loc_id,
            location_name=locations.get(loc_id, "Unknown"),
            **data,
        )
        for loc_id, data in by_loc.items()
        if loc_id in locations
    ]


@router.get("/forward-bookings", response_model=list[ForwardBookingWeek])
async def get_forward_bookings(
    weeks_forward: int = Query(4, ge=1, le=26),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Forward bookings from BigQuery for the next N weeks."""
    from datetime import date as dt_date

    from app.connectors.bigquery import BigQueryClient

    today = dt_date.today().isoformat()
    # FIX(L30): handle BigQuery errors gracefully
    try:
        client = BigQueryClient()
        rows = client.get_forward_bookings(today, weeks_forward)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"BigQuery query failed: {str(exc)[:200]}")

    result = await db.execute(
        select(PropertyMapping).where(PropertyMapping.is_active.is_(True))
    )
    mappings = result.scalars().all()
    bq_to_loc: dict[int, uuid.UUID] = {}
    for m in mappings:
        if m.location_id:
            bq_to_loc[m.bigquery_property_id] = m.location_id

    result = await db.execute(select(Location).where(Location.is_active.is_(True)))
    loc_names = {loc.id: loc.name for loc in result.scalars().all()}

    out = []
    for row in rows:
        bq_id = int(row["property_id"])
        loc_id = bq_to_loc.get(bq_id)
        out.append(ForwardBookingWeek(
            property_name=str(row["property_name"]),
            location_id=loc_id,
            location_name=loc_names.get(loc_id) if loc_id else None,
            service_type=str(row["service_type"]),
            week_start=row["week_start"],
            pet_days_booked=int(row.get("pet_days_booked", 0)),
            revenue_booked=float(row.get("revenue_booked", 0) or 0),
        ))
    return out


@router.get("/mappings", response_model=list[PropertyMappingRead])
async def list_property_mappings(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """List all BigQuery → KipFP property mappings."""
    result = await db.execute(
        select(PropertyMapping).order_by(PropertyMapping.bigquery_property_name)
    )
    return result.scalars().all()
