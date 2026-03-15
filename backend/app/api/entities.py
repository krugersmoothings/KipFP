from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.deps import get_db, require_finance
from app.db.models.entity import Entity
from app.db.models.location import Location
from app.db.models.user import User
from app.schemas.entity import EntityRead, LocationRead

router = APIRouter(prefix="/entities", tags=["entities"])

MONTH_ABBR = [
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
]


@router.get("", response_model=list[EntityRead])
async def list_entities(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return all active entities."""
    result = await db.execute(
        select(Entity)
        .where(Entity.is_active.is_(True))
        .order_by(Entity.code)
    )
    return result.scalars().all()


@router.get("/locations", response_model=list[LocationRead])
async def list_locations(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return all active locations."""
    result = await db.execute(
        select(Location)
        .where(Location.is_active.is_(True))
        .order_by(Location.state, Location.name)
    )
    return result.scalars().all()


def _netsuite_tb_url(
    account_id: str,
    subsidiary_id: str,
    fy_year: int,
    fy_month: int,
) -> str:
    """Construct a NetSuite Trial Balance report URL filtered by subsidiary
    and period.  Uses the standard report runner with the built-in TB report."""
    cal_year = fy_year - 1 if fy_month <= 6 else fy_year
    cal_month = ((fy_month + 5) % 12) + 1

    # NetSuite date format for period filter: M/YYYY
    period_str = f"{cal_month}/{cal_year}"
    base = f"https://{account_id}.app.netsuite.com"
    return (
        f"{base}/app/reporting/reportrunner.nl"
        f"?accttype=-1"
        f"&subsidiary={subsidiary_id}"
        f"&periodrange={period_str}"
    )


@router.get("/netsuite-urls")
async def get_netsuite_urls(
    account_code: str = Query(...),
    fy_year: int = Query(...),
    fy_month: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
) -> dict[str, str]:
    """Return a map of entity_code -> NetSuite trial balance URL for entities
    that have a source_entity_id (i.e. are synced from NetSuite)."""
    ns_account_id = settings.NETSUITE_ACCOUNT_ID
    if not ns_account_id:
        return {}

    result = await db.execute(
        select(Entity).where(
            Entity.is_active.is_(True),
            Entity.source_entity_id.isnot(None),
        )
    )
    entities = result.scalars().all()

    urls: dict[str, str] = {}
    for ent in entities:
        if ent.source_entity_id:
            urls[ent.code] = _netsuite_tb_url(
                ns_account_id,
                ent.source_entity_id,
                fy_year,
                fy_month,
            )
    return urls
