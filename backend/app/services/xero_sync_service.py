"""Xero → je_lines sync service.

Mirrors netsuite_sync_service but pulls trial balance data from Xero.
Xero uses account names (not codes) as source_account_code in je_lines.
"""

import calendar
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.connectors.xero import get_authenticated_client
from app.db.base import async_session_factory
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine, SyncRun, SyncStatus, SyncTrigger
from app.services.netsuite_sync_service import fy_to_calendar

logger = logging.getLogger(__name__)


async def sync_entity(
    entity_id: str | uuid.UUID,
    fy_year: int,
    fy_month: int,
    sync_run_id: str | uuid.UUID | None = None,
    triggered_by: SyncTrigger = SyncTrigger.manual,
) -> uuid.UUID:
    """Pull a trial balance from Xero and upsert into je_lines.

    Returns the sync_run id.
    """
    entity_id = uuid.UUID(str(entity_id))
    run_id = uuid.UUID(str(sync_run_id)) if sync_run_id else uuid.uuid4()

    async with async_session_factory() as db:
        existing = await db.get(SyncRun, run_id)
        if existing:
            run = existing
            run.status = SyncStatus.running
            run.started_at = datetime.now(timezone.utc)
        else:
            run = SyncRun(
                id=run_id,
                entity_id=entity_id,
                source_system="xero",
                started_at=datetime.now(timezone.utc),
                status=SyncStatus.running,
                triggered_by=triggered_by,
            )
            db.add(run)
        await db.flush()

        try:
            entity = await db.get(Entity, entity_id)
            if entity is None:
                raise ValueError(f"Entity {entity_id} not found")

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

            from_date = date(cal_year, cal_month, 1)
            last_day = calendar.monthrange(cal_year, cal_month)[1]
            to_date = date(cal_year, cal_month, last_day)

            client = await get_authenticated_client()
            rows = await client.get_trial_balance(from_date, to_date)
            logger.info(
                "Xero returned %d TB rows for entity=%s period=FY%dM%02d",
                len(rows), entity.code, fy_year, fy_month,
            )

            upserted = 0
            for row in rows:
                debit = Decimal(str(row.get("Debit", 0) or 0))
                credit = Decimal(str(row.get("Credit", 0) or 0))
                amount = debit - credit

                source_key = str(row.get("AccountName", ""))

                from sqlalchemy import func
                stmt = insert(JeLine).values(
                    id=uuid.uuid4(),
                    entity_id=entity_id,
                    period_id=period.id,
                    source_account_code=source_key,
                    source_account_name=source_key,
                    amount=amount,
                    sync_run_id=run_id,
                    source_ref=str(row.get("AccountID", "")),
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

            run.status = SyncStatus.success
            run.records_upserted = upserted
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(
                "Xero sync complete entity=%s FY%dM%02d — %d rows upserted",
                entity.code, fy_year, fy_month, upserted,
            )

        except Exception as exc:
            logger.exception("Xero sync failed for entity_id=%s", entity_id)
            run.status = SyncStatus.failed
            run.error_detail = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

    return run_id
