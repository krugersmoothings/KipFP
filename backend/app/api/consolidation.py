import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, require_finance
from app.db.models.account import Account, Statement
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.user import User
from app.schemas.consolidation import (
    ConsolidatedLineItem,
    ConsolidationRunRead,
    ConsolidationTriggerResponse,
    EntityBreakdown,
)

router = APIRouter(tags=["consolidation"])


@router.post(
    "/consolidate/{fy_year}/{fy_month}",
    response_model=ConsolidationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_consolidation(
    fy_year: int,
    fy_month: int,
    _user: User = Depends(require_admin),
):
    """Trigger consolidation for a period via Celery."""
    from app.worker import consolidate_period_task

    task = consolidate_period_task.delay(fy_year, fy_month)
    return ConsolidationTriggerResponse(
        consolidation_run_id=uuid.UUID(int=0),
        status="queued",
    )


@router.get(
    "/consolidated/is",
    response_model=list[ConsolidatedLineItem],
)
async def get_consolidated_is(
    fy_year: int = Query(...),
    fy_month: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return consolidated Income Statement for a period."""
    return await _get_statement(db, fy_year, fy_month, Statement.is_)


@router.get(
    "/consolidated/bs",
    response_model=list[ConsolidatedLineItem],
)
async def get_consolidated_bs(
    fy_year: int = Query(...),
    fy_month: int = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return consolidated Balance Sheet for a period."""
    return await _get_statement(db, fy_year, fy_month, Statement.bs)


async def _get_statement(
    db: AsyncSession,
    fy_year: int,
    fy_month: int,
    statement: Statement,
) -> list[ConsolidatedLineItem]:
    result = await db.execute(
        select(Period).where(
            Period.fy_year == fy_year,
            Period.fy_month == fy_month,
        )
    )
    period = result.scalar_one_or_none()
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    result = await db.execute(
        select(Account)
        .where(Account.statement == statement)
        .order_by(Account.sort_order)
    )
    accounts = result.scalars().all()

    result = await db.execute(
        select(ConsolidatedActual).where(
            ConsolidatedActual.period_id == period.id,
        )
    )
    actuals = result.scalars().all()

    result = await db.execute(select(Entity))
    entities = {e.id: e for e in result.scalars().all()}

    group_by_acct: dict[uuid.UUID, float] = {}
    entity_by_acct: dict[uuid.UUID, list[EntityBreakdown]] = {}

    for actual in actuals:
        if actual.is_group_total:
            group_by_acct[actual.account_id] = float(actual.amount)
        else:
            if actual.account_id not in entity_by_acct:
                entity_by_acct[actual.account_id] = []
            ent = entities.get(actual.entity_id)
            entity_by_acct[actual.account_id].append(EntityBreakdown(
                entity_id=actual.entity_id,
                entity_code=ent.code if ent else "?",
                amount=float(actual.amount),
            ))

    items: list[ConsolidatedLineItem] = []
    for acct in accounts:
        items.append(ConsolidatedLineItem(
            account_code=acct.code,
            account_name=acct.name,
            amount=group_by_acct.get(acct.id, 0.0),
            is_subtotal=acct.is_subtotal,
            entity_breakdown=entity_by_acct.get(acct.id, []),
        ))

    return items
