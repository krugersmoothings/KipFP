import asyncio
import logging

from celery import Celery
from celery.schedules import crontab

from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "kipfp",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Australia/Sydney",
    enable_utc=True,
    beat_schedule={
        "sync-all-netsuite-daily": {
            "task": "app.worker.sync_all_netsuite",
            "schedule": crontab(hour=2, minute=0),
        },
        "sync-bigquery-nightly": {
            "task": "app.worker.sync_bigquery_nightly",
            "schedule": crontab(hour=3, minute=0),
        },
    },
)


# ── NetSuite tasks ────────────────────────────────────────────────────────────


@celery_app.task(name="app.worker.sync_entity_task")
def sync_entity_task(
    entity_id: str,
    fy_year: int,
    fy_month: int,
    sync_run_id: str | None = None,
):
    """Sync a single entity+period from NetSuite (called by the API endpoint)."""
    from app.services.netsuite_sync_service import sync_entity

    asyncio.run(sync_entity(entity_id, fy_year, fy_month, sync_run_id))
    _trigger_auto_consolidation(fy_year, fy_month)


@celery_app.task(name="app.worker.sync_all_netsuite")
def sync_all_netsuite():
    """Scheduled: sync every active NetSuite entity for the last 2 unlocked periods."""
    asyncio.run(_sync_all())


async def _sync_all():
    from sqlalchemy import select

    from app.db.base import async_session_factory
    from app.db.models.entity import Entity, SourceSystem
    from app.db.models.period import Period
    from app.db.models.sync import SyncTrigger
    from app.services.netsuite_sync_service import sync_entity

    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity).where(
                Entity.source_system == SourceSystem.netsuite,
                Entity.is_active.is_(True),
            )
        )
        entities = result.scalars().all()

        result = await db.execute(
            select(Period)
            .where(Period.is_locked.is_(False))
            .order_by(Period.fy_year.desc(), Period.fy_month.desc())
            .limit(2)
        )
        periods = result.scalars().all()

    consolidated_periods = set()
    for entity in entities:
        for period in periods:
            try:
                await sync_entity(
                    entity.id,
                    period.fy_year,
                    period.fy_month,
                    triggered_by=SyncTrigger.schedule,
                )
                consolidated_periods.add((period.fy_year, period.fy_month))
            except Exception:
                logger.exception(
                    "Scheduled sync failed for %s FY%dM%02d",
                    entity.code, period.fy_year, period.fy_month,
                )

    from app.services.consolidation_engine import consolidate_period
    for fy_year, fy_month in consolidated_periods:
        try:
            await consolidate_period(fy_year, fy_month)
        except Exception:
            logger.exception(
                "Auto-consolidation failed FY%dM%02d", fy_year, fy_month
            )


# ── Xero tasks ────────────────────────────────────────────────────────────────


@celery_app.task(name="app.worker.sync_xero_entity_task")
def sync_xero_entity_task(
    entity_id: str,
    fy_year: int,
    fy_month: int,
    sync_run_id: str | None = None,
):
    """Sync a single entity+period from Xero."""
    from app.services.xero_sync_service import sync_entity

    asyncio.run(sync_entity(entity_id, fy_year, fy_month, sync_run_id))
    _trigger_auto_consolidation(fy_year, fy_month)


# ── Consolidation tasks ──────────────────────────────────────────────────────


@celery_app.task(name="app.worker.consolidate_period_task")
def consolidate_period_task(fy_year: int, fy_month: int, include_aasb16: bool = True):
    """Run consolidation for a period."""
    from app.services.consolidation_engine import consolidate_period

    asyncio.run(consolidate_period(fy_year, fy_month, include_aasb16=include_aasb16))


def _trigger_auto_consolidation(fy_year: int, fy_month: int):
    """Fire-and-forget consolidation after a successful sync."""
    try:
        consolidate_period_task.delay(fy_year, fy_month)
        logger.info(
            "Auto-consolidation queued for FY%dM%02d", fy_year, fy_month,
        )
    except Exception:
        logger.exception(
            "Failed to queue auto-consolidation for FY%dM%02d",
            fy_year, fy_month,
        )


# ── BigQuery tasks ────────────────────────────────────────────────────────────


@celery_app.task(name="app.worker.sync_bigquery_task")
def sync_bigquery_task(
    date_from: str,
    date_to: str,
    sync_run_id: str | None = None,
):
    """Sync pet days from BigQuery for a date range (called by API endpoint)."""
    from app.services.bigquery_sync_service import sync_pet_days

    asyncio.run(sync_pet_days(date_from, date_to, sync_run_id))


@celery_app.task(name="app.worker.sync_bigquery_nightly")
def sync_bigquery_nightly():
    """Scheduled: pull last 90 days of pet days from BigQuery at 3 AM AEST."""
    from datetime import date, timedelta

    from app.db.models.sync import SyncTrigger
    from app.services.bigquery_sync_service import sync_pet_days

    today = date.today()
    date_from = (today - timedelta(days=90)).isoformat()
    date_to = today.isoformat()

    try:
        asyncio.run(sync_pet_days(date_from, date_to, triggered_by=SyncTrigger.schedule))
        logger.info("Nightly BigQuery sync complete (%s to %s)", date_from, date_to)
    except Exception:
        logger.exception("Nightly BigQuery sync failed")


# ── Budget model tasks ────────────────────────────────────────────────────────


@celery_app.task(name="app.worker.calculate_all_sites_task")
def calculate_all_sites_task(version_id: str):
    """Calculate weekly budget for all sites, roll up, then run model."""
    import uuid as _uuid

    from app.services.site_budget_engine import calculate_all_sites

    vid = _uuid.UUID(version_id)
    result = asyncio.run(calculate_all_sites(vid))

    from app.services.model_engine import run_model
    asyncio.run(run_model(vid))

    return result


@celery_app.task(name="app.worker.run_model_task", bind=True)
def run_model_task(self, version_id: str):
    """Run the full budget model engine for a version."""
    import uuid as _uuid

    from app.services.model_engine import run_model

    vid = _uuid.UUID(version_id)
    return asyncio.run(run_model(vid))
