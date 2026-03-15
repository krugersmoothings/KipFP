from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_finance
from app.db.models.account import Account, Statement
from app.db.models.consolidation import ConsolidatedActual
from app.db.models.period import Period
from app.db.models.sync import SyncRun, SyncStatus
from app.db.models.user import User
from app.schemas.consolidation import DashboardKPIs

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

KPI_CODES = {
    "revenue": "REV-SALES",
    "gm": "GM",
    "ebitda": "EBITDA",
    "cash": "BS-CASH",
    "debt": "BS-TOTALDEBT",
}


async def _acct_amount(
    db, account_code: str, period_id, *, group_total: bool = True,
) -> float:
    """Sum consolidated amount for an account in a period."""
    stmt = (
        select(func.coalesce(func.sum(ConsolidatedActual.amount), 0))
        .join(Account, ConsolidatedActual.account_id == Account.id)
        .where(
            Account.code == account_code,
            ConsolidatedActual.period_id == period_id,
            ConsolidatedActual.is_group_total == group_total,
        )
    )
    result = await db.execute(stmt)
    return float(result.scalar())


async def _ytd_amount(db, account_code: str, period_ids: list) -> float:
    stmt = (
        select(func.coalesce(func.sum(ConsolidatedActual.amount), 0))
        .join(Account, ConsolidatedActual.account_id == Account.id)
        .where(
            Account.code == account_code,
            ConsolidatedActual.period_id.in_(period_ids),
            ConsolidatedActual.is_group_total.is_(True),
        )
    )
    result = await db.execute(stmt)
    return float(result.scalar())


@router.get("/kpis", response_model=DashboardKPIs)
async def get_dashboard_kpis(
    fy_year: int = Query(...),
    fy_month: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return dashboard KPI values for the selected period."""
    # Current period
    result = await db.execute(
        select(Period).where(Period.fy_year == fy_year, Period.fy_month == fy_month)
    )
    period = result.scalar_one_or_none()
    if period is None:
        return DashboardKPIs()

    # YTD period ids (M01 through selected month)
    result = await db.execute(
        select(Period.id).where(
            Period.fy_year == fy_year,
            Period.fy_month <= fy_month,
        )
    )
    ytd_ids = [r[0] for r in result.all()]

    # Prior comparable period (same month, prior FY)
    result = await db.execute(
        select(Period).where(
            Period.fy_year == fy_year - 1,
            Period.fy_month == fy_month,
        )
    )
    pcp = result.scalar_one_or_none()

    # P&L accounts are credit-normal (stored negative) — negate for display
    revenue_mtd = -await _acct_amount(db, KPI_CODES["revenue"], period.id)
    revenue_pcp = -await _acct_amount(db, KPI_CODES["revenue"], pcp.id) if pcp else 0

    gm_mtd = -await _acct_amount(db, KPI_CODES["gm"], period.id)
    gm_pct = (gm_mtd / revenue_mtd * 100) if revenue_mtd else None

    gm_pcp_val = -await _acct_amount(db, KPI_CODES["gm"], pcp.id) if pcp else 0
    gm_pct_pcp = (gm_pcp_val / revenue_pcp * 100) if revenue_pcp else None

    ebitda_mtd = -await _acct_amount(db, KPI_CODES["ebitda"], period.id)
    ebitda_ytd = -await _ytd_amount(db, KPI_CODES["ebitda"], ytd_ids)

    net_cash = await _acct_amount(db, KPI_CODES["cash"], period.id)
    total_debt = await _acct_amount(db, KPI_CODES["debt"], period.id)

    # Last successful sync
    result = await db.execute(
        select(SyncRun.completed_at)
        .where(SyncRun.status == SyncStatus.success)
        .order_by(SyncRun.completed_at.desc().nullslast())
        .limit(1)
    )
    last_sync = result.scalar_one_or_none()

    return DashboardKPIs(
        revenue_mtd=revenue_mtd,
        revenue_pcp=revenue_pcp,
        gm_pct=gm_pct,
        gm_pct_pcp=gm_pct_pcp,
        ebitda_mtd=ebitda_mtd,
        ebitda_ytd=ebitda_ytd,
        net_cash=net_cash,
        total_debt=total_debt,
        last_sync_at=last_sync,
    )
