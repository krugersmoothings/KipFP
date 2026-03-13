import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, require_finance
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
    """Trigger a NetSuite trial balance sync for one entity + period.

    Creates a sync_run record immediately, then dispatches the work to a
    Celery worker so the HTTP response returns fast.
    """
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


@router.get("/runs", response_model=list[SyncRunRead])
async def list_sync_runs(
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return the 20 most recent sync runs."""
    result = await db.execute(
        select(SyncRun)
        .order_by(SyncRun.started_at.desc().nullslast())
        .limit(20)
    )
    return result.scalars().all()


@router.get("/runs/{run_id}", response_model=SyncRunRead)
async def get_sync_run(
    run_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return a single sync run by id."""
    run = await db.get(SyncRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Sync run not found")
    return run
