"""Opening-balance sync service.

Pulls a cumulative trial balance as at the end of the month *before* FY start
(i.e. June 30 for Australian FY) and stores the balances in ``je_lines`` for a
special ``fy_month=0`` period.  These rows feed into the consolidation engine
and allow the balance sheet to show correct point-in-time balances.
"""

import calendar
import logging
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.connectors.netsuite import NetSuiteClient
from app.connectors.xero import get_authenticated_client
from app.db.base import async_session_factory
from app.db.models.entity import Entity, SourceSystem
from app.db.models.period import Period
from app.db.models.sync import JeLine, SyncRun, SyncStatus, SyncTrigger
from app.services.netsuite_sync_service import fy_to_calendar

logger = logging.getLogger(__name__)


async def _ensure_ob_period(db, fy_year: int) -> Period:
    """Return (or create) the fy_month=0 opening-balance period for *fy_year*.

    The period dates cover the last day of the prior FY (June 30).
    """
    result = await db.execute(
        select(Period).where(Period.fy_year == fy_year, Period.fy_month == 0)
    )
    period = result.scalar_one_or_none()
    if period is not None:
        return period

    cal_year = fy_year - 1
    ob_date = date(cal_year, 6, 30)
    period = Period(
        id=uuid.uuid4(),
        fy_year=fy_year,
        fy_month=0,
        calendar_year=cal_year,
        calendar_month=6,
        period_start=ob_date,
        period_end=ob_date,
        is_locked=True,
    )
    db.add(period)
    await db.flush()
    return period


async def sync_opening_balance(
    entity_id: str | uuid.UUID,
    fy_year: int,
    triggered_by: SyncTrigger = SyncTrigger.manual,
) -> uuid.UUID:
    """Pull a cumulative TB as at June 30 before *fy_year* and store in je_lines.

    Works for both NetSuite and Xero entities (detected via ``source_system``).
    Returns the sync_run id.
    """
    entity_id = uuid.UUID(str(entity_id))
    run_id = uuid.uuid4()

    async with async_session_factory() as db:
        run = SyncRun(
            id=run_id,
            entity_id=entity_id,
            source_system=None,
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

            # FIX(M18): ensure source_system is a valid DB enum value
            if entity.source_system and entity.source_system.value in ("netsuite", "xero"):
                run.source_system = entity.source_system.value
            else:
                run.source_system = "netsuite"

            period = await _ensure_ob_period(db, fy_year)

            ob_cal_year = fy_year - 1
            ob_cal_month = 6
            ob_date = date(ob_cal_year, ob_cal_month, 30)

            if entity.source_system == SourceSystem.xero:
                rows = await _pull_xero_ob(entity, ob_date)
            else:
                rows = await _pull_netsuite_ob(entity, ob_cal_year, ob_cal_month)

            logger.info(
                "Opening balance returned %d rows for entity=%s FY%d OB",
                len(rows), entity.code, fy_year,
            )

            upserted = 0
            for row in rows:
                stmt = insert(JeLine).values(
                    id=uuid.uuid4(),
                    entity_id=entity_id,
                    period_id=period.id,
                    source_account_code=row["source_account_code"],
                    source_account_name=row.get("source_account_name", ""),
                    amount=row["amount"],
                    sync_run_id=run_id,
                    source_ref=row.get("source_ref", ""),
                    location_id=None,
                    is_aasb16=row.get("is_aasb16", False),
                    is_opening_balance=True,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_je_lines_entity_period_account_aasb16",
                    set_={
                        "amount": stmt.excluded.amount,
                        "source_account_name": stmt.excluded.source_account_name,
                        "sync_run_id": stmt.excluded.sync_run_id,
                        "source_ref": stmt.excluded.source_ref,
                        "is_opening_balance": True,
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
                "OB sync complete entity=%s FY%d — %d rows upserted",
                entity.code, fy_year, upserted,
            )

        except Exception as exc:
            logger.exception(
                "OB sync failed for entity_id=%s FY%d", entity_id, fy_year,
            )
            run.status = SyncStatus.failed
            run.error_detail = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

    return run_id


async def _pull_netsuite_ob(
    entity: Entity,
    cal_year: int,
    cal_month: int,
) -> list[dict]:
    """Fetch cumulative TB from NetSuite as at the end of *cal_month*."""
    if not entity.source_entity_id:
        raise ValueError(
            f"Entity {entity.code} has no source_entity_id "
            "(NetSuite subsidiary internal id)"
        )
    client = NetSuiteClient()
    raw = await client.get_trial_balance_as_at(
        entity.source_entity_id, cal_year, cal_month,
    )
    rows: list[dict] = []
    for r in raw:
        amount = Decimal(str(r.get("amount", 0) or 0))
        class_name = str(r.get("class_name") or "")
        is_aasb16 = class_name.strip().upper().replace(" ", "") == "AASB16"
        rows.append({
            "source_account_code": str(r.get("acctnumber", "")),
            "source_account_name": str(r.get("fullname", "")),
            "amount": amount,
            "source_ref": str(r.get("accttype", "")),
            "is_aasb16": is_aasb16,
        })
    return rows


async def _pull_xero_ob(entity: Entity, as_at: date) -> list[dict]:
    """Fetch cumulative TB snapshot from Xero as at *as_at*."""
    client = await get_authenticated_client()
    tb = await client.get_trial_balance_at_date(as_at)
    rows: list[dict] = []
    for name, info in tb.items():
        amount = Decimal(str(info.get("amount", 0)))
        if abs(amount) < Decimal("0.005"):
            continue
        rows.append({
            "source_account_code": name,
            "source_account_name": info.get("raw", name),
            "amount": amount,
            "source_ref": str(info.get("id", "")),
            "is_aasb16": False,
        })
    return rows
