"""NetSuite → je_lines sync service.

Pulls trial balance data from NetSuite via SuiteQL and upserts rows
into the ``je_lines`` table, tracking each run in ``sync_runs``.
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.connectors.netsuite import NetSuiteClient
from app.db.base import async_session_factory
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine, SyncRun, SyncStatus, SyncTrigger

logger = logging.getLogger(__name__)


def fy_to_calendar(fy_year: int, fy_month: int) -> tuple[int, int]:
    """Convert Australian financial-year month to calendar year/month.

    FY month 1 = Jul, so fy_month 1 of fy_year 2024 → Jul 2023.

        fy_month 1-6  → calendar_month = fy_month + 6, calendar_year = fy_year - 1
        fy_month 7-12 → calendar_month = fy_month - 6, calendar_year = fy_year
    """
    if fy_month <= 6:
        return fy_year - 1, fy_month + 6
    return fy_year, fy_month - 6


async def sync_entity(
    entity_id: str | uuid.UUID,
    fy_year: int,
    fy_month: int,
    sync_run_id: str | uuid.UUID | None = None,
    triggered_by: SyncTrigger = SyncTrigger.manual,
) -> uuid.UUID:
    """Pull a trial balance from NetSuite and upsert into je_lines.

    If *sync_run_id* references an existing ``sync_runs`` row (e.g. pre-created
    by the API endpoint), it is reused.  Otherwise a new row is inserted.

    Returns the sync_run id.
    """
    entity_id = uuid.UUID(str(entity_id))
    run_id = uuid.UUID(str(sync_run_id)) if sync_run_id else uuid.uuid4()

    async with async_session_factory() as db:
        # 1. Create / reuse sync_run ──────────────────────────────────────
        existing = await db.get(SyncRun, run_id)
        if existing:
            run = existing
            run.status = SyncStatus.running
            run.started_at = datetime.now(timezone.utc)
        else:
            run = SyncRun(
                id=run_id,
                entity_id=entity_id,
                source_system="netsuite",
                started_at=datetime.now(timezone.utc),
                status=SyncStatus.running,
                triggered_by=triggered_by,
            )
            db.add(run)
        await db.flush()

        try:
            # 2. Look up entity → NS subsidiary id ───────────────────────
            entity = await db.get(Entity, entity_id)
            if entity is None:
                raise ValueError(f"Entity {entity_id} not found")
            if not entity.source_entity_id:
                raise ValueError(
                    f"Entity {entity.code} has no source_entity_id "
                    "(NetSuite subsidiary internal id)"
                )
            subsidiary_id = entity.source_entity_id

            # 3. Convert FY → calendar month ─────────────────────────────
            cal_year, cal_month = fy_to_calendar(fy_year, fy_month)

            result = await db.execute(
                select(Period).where(
                    Period.fy_year == fy_year,
                    Period.fy_month == fy_month,
                )
            )
            period = result.scalar_one_or_none()
            if period is None:
                raise ValueError(
                    f"Period FY{fy_year} M{fy_month} not found in periods table"
                )

            # 4. Fetch trial balance from NetSuite ────────────────────────
            client = NetSuiteClient()
            rows = await client.get_trial_balance(
                subsidiary_id, cal_year, cal_month,
            )
            logger.info(
                "NetSuite returned %d TB rows for entity=%s period=FY%dM%02d",
                len(rows), entity.code, fy_year, fy_month,
            )

            # 5. Upsert je_lines ─────────────────────────────────────────
            upserted = 0
            for row in rows:
                debit = Decimal(str(row.get("debit", 0) or 0))
                credit = Decimal(str(row.get("credit", 0) or 0))
                amount = debit - credit

                stmt = insert(JeLine).values(
                    id=uuid.uuid4(),
                    entity_id=entity_id,
                    period_id=period.id,
                    source_account_code=str(row.get("acctnumber", "")),
                    source_account_name=str(row.get("fullname", "")),
                    amount=amount,
                    sync_run_id=run_id,
                    source_ref=str(row.get("type", "")),
                    location_id=None,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_je_lines_entity_period_account",
                    set_={
                        "amount": stmt.excluded.amount,
                        "source_account_name": stmt.excluded.source_account_name,
                        "sync_run_id": stmt.excluded.sync_run_id,
                        "source_ref": stmt.excluded.source_ref,
                        "ingested_at": func.now(),
                    },
                )
                await db.execute(stmt)
                upserted += 1

            # 6. Mark success ─────────────────────────────────────────────
            run.status = SyncStatus.success
            run.records_upserted = upserted
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Sync complete entity=%s FY%dM%02d — %d rows upserted",
                entity.code, fy_year, fy_month, upserted,
            )

        except Exception as exc:
            # 7. Mark failed ──────────────────────────────────────────────
            logger.exception("Sync failed for entity_id=%s", entity_id)
            run.status = SyncStatus.failed
            run.error_detail = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

    return run_id
