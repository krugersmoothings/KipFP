"""BigQuery → site_pet_days sync service.

Pulls pet-day and revenue data from BigQuery via the PetBooking dataset,
maps BigQuery property IDs to KipFP locations via the property_mappings
table, and upserts into site_pet_days.
"""

import logging
import uuid
from collections import defaultdict
from datetime import date as date_type, datetime, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from app.connectors.bigquery import BigQueryClient
from app.db.base import async_session_factory
from app.db.models.location import PropertyMapping
from app.db.models.pet_days import ServiceType, SitePetDay
from app.db.models.sync import SyncRun, SyncStatus, SyncTrigger

logger = logging.getLogger(__name__)

VALID_SERVICE_TYPES = {e.value for e in ServiceType}


async def sync_pet_days(
    date_from: str,
    date_to: str,
    sync_run_id: str | uuid.UUID | None = None,
    triggered_by: SyncTrigger = SyncTrigger.manual,
) -> uuid.UUID:
    """Pull pet days + revenue from BigQuery and upsert into site_pet_days.

    Parameters
    ----------
    date_from, date_to : str
        YYYY-MM-DD date strings.
    sync_run_id : optional
        Pre-created sync_run row to reuse.
    triggered_by : SyncTrigger
        Whether this is a manual or scheduled sync.

    Returns the sync_run id.
    """
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
                entity_id=None,
                source_system="bigquery",
                started_at=datetime.now(timezone.utc),
                status=SyncStatus.running,
                triggered_by=triggered_by,
            )
            db.add(run)
        await db.flush()

        try:
            result = await db.execute(
                select(PropertyMapping).where(PropertyMapping.is_active.is_(True))
            )
            mappings = result.scalars().all()
            bq_to_location: dict[int, uuid.UUID] = {}
            for m in mappings:
                if m.location_id:
                    bq_to_location[m.bigquery_property_id] = m.location_id

            if not bq_to_location:
                raise ValueError("No active property mappings with location_id found")

            logger.info(
                "Loaded %d property mappings, syncing %s to %s",
                len(bq_to_location), date_from, date_to,
            )

            import asyncio

            client = BigQueryClient()
            loop = asyncio.get_running_loop()
            pet_day_rows = await loop.run_in_executor(None, client.get_pet_days, date_from, date_to)
            revenue_rows = await loop.run_in_executor(None, client.get_revenue, date_from, date_to)

            logger.info(
                "BigQuery returned %d pet-day rows, %d revenue rows",
                len(pet_day_rows), len(revenue_rows),
            )

            revenue_lookup: dict[tuple, Decimal] = {}
            for row in revenue_rows:
                key = (
                    int(row["property_id"]),
                    str(row["date"]),
                    str(row.get("service_type", "")).lower().strip(),
                )
                revenue_lookup[key] = Decimal(str(row.get("revenue_aud", 0) or 0))

            upserted = 0
            skipped = 0
            for row in pet_day_rows:
                bq_prop_id = int(row["property_id"])
                location_id = bq_to_location.get(bq_prop_id)
                if location_id is None:
                    skipped += 1
                    continue

                svc_type = str(row.get("service_type", "")).lower().strip()
                if svc_type not in VALID_SERVICE_TYPES:
                    skipped += 1
                    continue

                raw_date = row["date"]
                if isinstance(raw_date, str):
                    row_date = date_type.fromisoformat(raw_date)
                elif isinstance(raw_date, datetime):
                    row_date = raw_date.date()
                else:
                    row_date = raw_date
                pet_days_count = int(row.get("pet_days", 0))
                rev_key = (bq_prop_id, str(raw_date), svc_type)
                revenue = revenue_lookup.get(rev_key, Decimal("0"))

                stmt = insert(SitePetDay).values(
                    id=uuid.uuid4(),
                    location_id=location_id,
                    date=row_date,
                    service_type=svc_type,
                    pet_days=pet_days_count,
                    revenue_aud=revenue,
                    sync_run_id=run_id,
                )
                stmt = stmt.on_conflict_do_update(
                    constraint="uq_site_pet_days_loc_date_svc",
                    set_={
                        "pet_days": stmt.excluded.pet_days,
                        "revenue_aud": stmt.excluded.revenue_aud,
                        "sync_run_id": stmt.excluded.sync_run_id,
                        "ingested_at": func.now(),
                    },
                )
                await db.execute(stmt)
                upserted += 1

            run.status = SyncStatus.success
            run.records_upserted = upserted
            run.completed_at = datetime.now(timezone.utc)
            if skipped:
                run.error_detail = f"{skipped} rows skipped (unmapped property or invalid service type)"
            await db.commit()

            logger.info(
                "BigQuery sync complete — %d rows upserted, %d skipped",
                upserted, skipped,
            )

        except Exception as exc:
            logger.exception("BigQuery sync failed")
            run.status = SyncStatus.failed
            run.error_detail = str(exc)[:2000]
            run.completed_at = datetime.now(timezone.utc)
            await db.commit()

    return run_id
