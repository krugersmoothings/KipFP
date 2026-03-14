"""Sync MC (Xero) for all 12 FY2024 periods, then consolidate and verify.

Run from the backend container:
    python -m scripts.sync_mc_fy2024
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.entity import Entity
from app.db.models.sync import JeLine
from app.db.models.period import Period


async def run():
    async with async_session_factory() as db:
        result = await db.execute(select(Entity).where(Entity.code == "MC"))
        mc = result.scalar_one_or_none()
        if mc is None:
            print("ERROR: MC entity not found")
            return
        print(f"MC entity: {mc.id} — {mc.name} (source={mc.source_system})")

    from app.services.xero_sync_service import sync_entity

    for fy_month in range(1, 13):
        print(f"\n--- Syncing FY2024 M{fy_month:02d} ---")
        try:
            run_id = await sync_entity(
                entity_id=str(mc.id),
                fy_year=2024,
                fy_month=fy_month,
            )
            print(f"  Sync run {run_id} complete")
        except Exception as exc:
            print(f"  FAILED: {exc}")

    async with async_session_factory() as db:
        result = await db.execute(
            select(func.count(JeLine.id)).where(JeLine.entity_id == mc.id)
        )
        total = result.scalar()
        print(f"\nTotal MC je_lines after sync: {total}")

        result = await db.execute(
            select(
                Period.fy_month,
                func.count(JeLine.id),
                func.sum(JeLine.amount),
            )
            .join(Period, JeLine.period_id == Period.id)
            .where(JeLine.entity_id == mc.id, Period.fy_year == 2024)
            .group_by(Period.fy_month)
            .order_by(Period.fy_month)
        )
        rows = result.all()
        print(f"\nMC je_lines by FY2024 month:")
        for fy_month, count, total_amt in rows:
            print(f"  M{fy_month:02d}: {count} lines, total amount={total_amt}")


if __name__ == "__main__":
    asyncio.run(run())
