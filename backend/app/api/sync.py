import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.deps import get_db, require_admin, require_finance
from app.db.models.entity import Entity
from app.db.models.sync import SyncRun, SyncStatus, SyncTrigger
from app.db.models.user import User
from app.schemas.sync import SyncRequest, SyncRunRead, SyncTriggerResponse

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post(
    "/netsuite/{entity_id}",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_netsuite_sync(
    entity_id: uuid.UUID,
    body: SyncRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Trigger a NetSuite trial balance sync for one entity + period."""
    from app.worker import sync_entity_task

    run_id = uuid.uuid4()

    run = SyncRun(
        id=run_id,
        entity_id=entity_id,
        source_system="netsuite",
        status=SyncStatus.running,
        triggered_by=SyncTrigger.manual,
    )
    db.add(run)
    await db.commit()

    sync_entity_task.delay(
        str(entity_id), body.fy_year, body.fy_month, str(run_id),
    )

    return SyncTriggerResponse(sync_run_id=run_id, status="queued")


@router.post(
    "/xero/{entity_id}",
    response_model=SyncTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_xero_sync(
    entity_id: uuid.UUID,
    body: SyncRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_admin),
):
    """Trigger a Xero trial balance sync for one entity + period."""
    from app.worker import sync_xero_entity_task

    run_id = uuid.uuid4()

    run = SyncRun(
        id=run_id,
        entity_id=entity_id,
        source_system="xero",
        status=SyncStatus.running,
        triggered_by=SyncTrigger.manual,
    )
    db.add(run)
    await db.commit()

    sync_xero_entity_task.delay(
        str(entity_id), body.fy_year, body.fy_month, str(run_id),
    )

    return SyncTriggerResponse(sync_run_id=run_id, status="queued")


@router.get("/runs", response_model=list[SyncRunRead])
async def list_sync_runs(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return the 50 most recent sync runs with entity info."""
    E = aliased(Entity)
    stmt = (
        select(
            SyncRun,
            E.code.label("entity_code"),
            E.name.label("entity_name"),
        )
        .outerjoin(E, SyncRun.entity_id == E.id)
        .order_by(SyncRun.started_at.desc().nullslast())
        .limit(50)
    )
    result = await db.execute(stmt)
    rows = result.all()

    return [
        SyncRunRead(
            id=run.id,
            entity_id=run.entity_id,
            entity_code=entity_code,
            entity_name=entity_name,
            source_system=run.source_system,
            started_at=run.started_at,
            completed_at=run.completed_at,
            status=run.status.value if run.status else None,
            records_upserted=run.records_upserted,
            error_detail=run.error_detail,
            triggered_by=run.triggered_by.value if run.triggered_by else "manual",
        )
        for run, entity_code, entity_name in rows
    ]


@router.get("/runs/{run_id}", response_model=SyncRunRead)
async def get_sync_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return a single sync run by id."""
    E = aliased(Entity)
    stmt = (
        select(
            SyncRun,
            E.code.label("entity_code"),
            E.name.label("entity_name"),
        )
        .outerjoin(E, SyncRun.entity_id == E.id)
        .where(SyncRun.id == run_id)
    )
    result = await db.execute(stmt)
    row = result.one_or_none()

    if row is None:
        raise HTTPException(status_code=404, detail="Sync run not found")

    run, entity_code, entity_name = row
    return SyncRunRead(
        id=run.id,
        entity_id=run.entity_id,
        entity_code=entity_code,
        entity_name=entity_name,
        source_system=run.source_system,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status.value if run.status else None,
        records_upserted=run.records_upserted,
        error_detail=run.error_detail,
        triggered_by=run.triggered_by.value if run.triggered_by else "manual",
    )
