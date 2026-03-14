"""Sync MC (Xero entity) for FY2025 M01-12 + FY2026 M01-07, then re-consolidate.

Run from the backend container:
    python -m scripts.sync_xero_mc
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import SyncRun, SyncStatus, JeLine
from app.services.xero_sync_service import sync_entity
from app.services.consolidation_engine import consolidate_period

ALL_PERIODS = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 8)]


async def run():
    async with async_session_factory() as db:
        result = await db.execute(select(Entity).where(Entity.code == "MC"))
        mc = result.scalar_one_or_none()
        if not mc:
            print("ERROR: MC entity not found")
            return
        print(f"MC entity: {mc.id} ({mc.name})")

    # Step 1: Sync
    print("\n" + "=" * 70)
    print("STEP 1: Syncing MC (Xero) for FY2025-FY2026")
    print("=" * 70)

    total = 0
    failed = 0
    for fy_year, fy_month in ALL_PERIODS:
        print(f"  FY{fy_year} M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await sync_entity(str(mc.id), fy_year, fy_month)
            async with async_session_factory() as db:
                srun = await db.get(SyncRun, run_id)
                if srun and srun.status == SyncStatus.failed:
                    err = (srun.error_detail or "unknown")[:120]
                    print(f"FAILED: {err}")
                    failed += 1
                else:
                    recs = srun.records_upserted if srun else 0
                    print(f"OK ({recs} rows)")
                    total += 1
        except Exception as exc:
            print(f"FAILED: {exc}")
            failed += 1

    print(f"\nSync complete: {total} succeeded, {failed} failed")

    # Step 2: Check for unmapped MC accounts
    print("\n" + "=" * 70)
    print("STEP 2: Unmapped MC accounts")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(
            select(AccountMapping.source_account_code)
            .where(AccountMapping.entity_id == mc.id)
        )
        mapped_codes = {r[0] for r in result.all()}

        result = await db.execute(
            select(
                JeLine.source_account_code,
                JeLine.source_account_name,
                func.sum(JeLine.amount),
                func.count(JeLine.id),
            )
            .join(Period, JeLine.period_id == Period.id)
            .where(
                JeLine.entity_id == mc.id,
                Period.fy_year.in_([2025, 2026]),
            )
            .group_by(JeLine.source_account_code, JeLine.source_account_name)
        )
        unmapped = []
        for code, name, total_amt, count in result.all():
            if code not in mapped_codes:
                unmapped.append((code, name, float(total_amt), count))

        unmapped.sort(key=lambda x: abs(x[2]), reverse=True)

        if unmapped:
            print(f"  {len(unmapped)} unmapped accounts:")
            for code, name, amt, count in unmapped:
                print(f"    {code:<45} {count:>4} lines  {amt:>14,.2f}")
        else:
            print("  All MC accounts are mapped!")

    # Step 3: Re-consolidate
    print("\n" + "=" * 70)
    print("STEP 3: Re-consolidating all 19 periods")
    print("=" * 70)

    for fy_year, fy_month in ALL_PERIODS:
        print(f"  FY{fy_year} M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(fy_year, fy_month)
            async with async_session_factory() as db:
                crun = await db.get(ConsolidationRun, run_id)
                status = crun.status.value if crun else "?"
                balanced = crun.bs_balanced if crun else None
                print(f"{status}, BS balanced={balanced}")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # Step 4: Revenue check
    print("\n" + "=" * 70)
    print("STEP 4: Revenue after MC inclusion")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(select(Account).where(Account.code == "REV-SALES"))
        rev = result.scalar_one()

        for fy_year, fy_month in ALL_PERIODS:
            result = await db.execute(
                select(Period).where(Period.fy_year == fy_year, Period.fy_month == fy_month)
            )
            period = result.scalar_one_or_none()
            if not period:
                continue
            result = await db.execute(
                select(func.coalesce(func.sum(ConsolidatedActual.amount), 0))
                .where(
                    ConsolidatedActual.period_id == period.id,
                    ConsolidatedActual.account_id == rev.id,
                    ConsolidatedActual.is_group_total.is_(True),
                )
            )
            amt = float(result.scalar())
            abs_amt = abs(amt)
            in_range = 1_750_000 <= abs_amt <= 3_500_000
            flag = "OK" if in_range else ("*** LOW" if abs_amt < 1_750_000 else "*** HIGH")
            print(f"  FY{fy_year} M{fy_month:02d}  {amt:>14,.2f}  {flag:>10}")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(run())
