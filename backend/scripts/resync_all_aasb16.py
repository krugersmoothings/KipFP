"""Re-sync all entities across all periods to populate is_aasb16 flag,
then re-consolidate everything.

Covers:
  - NetSuite entities: FY2024 M01-12, FY2025 M01-12, FY2026 M01-07
  - Xero MC entity:    FY2024 M01-12, FY2025 M01-12, FY2026 M01-07

Run from the backend container:
    python -m scripts.resync_all_aasb16
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.consolidation import ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine, SyncRun, SyncStatus
from app.services.netsuite_sync_service import sync_entity as sync_netsuite
from app.services.xero_sync_service import sync_entity as sync_xero
from app.services.consolidation_engine import consolidate_period

SYNC_RANGES: list[tuple[int, range]] = [
    (2024, range(1, 13)),
    (2025, range(1, 13)),
    (2026, range(1, 8)),
]

ALL_PERIODS: list[tuple[int, int]] = []
for fy_year, months in SYNC_RANGES:
    for m in months:
        ALL_PERIODS.append((fy_year, m))

MONTH_ABBR = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
              "Jan", "Feb", "Mar", "Apr", "May", "Jun"]


def _label(fy_year: int, fy_month: int) -> str:
    cal_year = fy_year - 1 if fy_month <= 6 else fy_year
    return f"{MONTH_ABBR[fy_month - 1]}-{cal_year % 100:02d}"


async def run():
    # ── 1. Load entities ─────────────────────────────────────────────────
    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity)
            .where(Entity.is_active.is_(True), Entity.source_system == "netsuite")
            .order_by(Entity.code)
        )
        ns_entities = list(result.scalars().all())

        result = await db.execute(
            select(Entity).where(Entity.code == "MC")
        )
        mc = result.scalar_one_or_none()

    print(f"NetSuite entities: {len(ns_entities)}")
    for e in ns_entities:
        print(f"  {e.code:>5}  {e.id}")
    if mc:
        print(f"\nXero MC entity: {mc.id} ({mc.name})")
    else:
        print("\nWARNING: MC entity not found — skipping Xero sync")

    total_periods = len(ALL_PERIODS)
    total_syncs = total_periods * len(ns_entities) + (total_periods if mc else 0)
    print(f"\nTotal: {total_periods} periods, {total_syncs} syncs to run\n")

    # ── 2. Sync NetSuite entities ────────────────────────────────────────
    print("=" * 70)
    print("STEP 1: Re-syncing all NetSuite entities (FY2024-FY2026)")
    print("=" * 70)

    ok_count = 0
    fail_count = 0

    for ent in ns_entities:
        print(f"\n>>> {ent.code} ({ent.name})")
        for fy_year, fy_month in ALL_PERIODS:
            print(f"  FY{fy_year} M{fy_month:02d} ({_label(fy_year, fy_month)}) ... ", end="", flush=True)
            try:
                run_id = await sync_netsuite(
                    entity_id=str(ent.id),
                    fy_year=fy_year,
                    fy_month=fy_month,
                )
                async with async_session_factory() as db:
                    srun = await db.get(SyncRun, run_id)
                    if srun and srun.status == SyncStatus.failed:
                        print(f"FAILED: {(srun.error_detail or '')[:120]}")
                        fail_count += 1
                    else:
                        recs = srun.records_upserted if srun else 0
                        print(f"OK ({recs} rows)")
                        ok_count += 1
            except Exception as exc:
                print(f"FAILED: {exc}")
                fail_count += 1

    print(f"\nNetSuite sync: {ok_count} OK, {fail_count} failed")

    # ── 3. Sync MC via Xero ──────────────────────────────────────────────
    if mc:
        print("\n" + "=" * 70)
        print("STEP 2: Re-syncing MC (Xero) for FY2024-FY2026")
        print("=" * 70)

        mc_ok = 0
        mc_fail = 0
        for fy_year, fy_month in ALL_PERIODS:
            print(f"  FY{fy_year} M{fy_month:02d} ({_label(fy_year, fy_month)}) ... ", end="", flush=True)
            try:
                run_id = await sync_xero(str(mc.id), fy_year, fy_month)
                async with async_session_factory() as db:
                    srun = await db.get(SyncRun, run_id)
                    if srun and srun.status == SyncStatus.failed:
                        print(f"FAILED: {(srun.error_detail or '')[:120]}")
                        mc_fail += 1
                    else:
                        recs = srun.records_upserted if srun else 0
                        print(f"OK ({recs} rows)")
                        mc_ok += 1
            except Exception as exc:
                print(f"FAILED: {exc}")
                mc_fail += 1

        print(f"\nXero MC sync: {mc_ok} OK, {mc_fail} failed")

    # ── 4. Re-consolidate all periods ────────────────────────────────────
    print("\n" + "=" * 70)
    print(f"STEP 3: Re-consolidating all {total_periods} periods")
    print("=" * 70)

    for fy_year, fy_month in ALL_PERIODS:
        print(f"  FY{fy_year} M{fy_month:02d} ({_label(fy_year, fy_month)}) ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(fy_year, fy_month)
            async with async_session_factory() as db:
                crun = await db.get(ConsolidationRun, run_id)
                status = crun.status.value if crun else "?"
                balanced = crun.bs_balanced if crun else None
                ic = crun.ic_alerts or ""
                ic_short = ic[:80] + "..." if len(ic) > 80 else ic
                print(f"{status}, BS balanced={balanced}" +
                      (f"  IC: {ic_short}" if ic else ""))
        except Exception as exc:
            print(f"FAILED: {exc}")

    # ── 5. AASB16 verification ───────────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 4: AASB16 verification — is_aasb16 rows by period")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(
            select(
                Period.fy_year,
                Period.fy_month,
                func.count(JeLine.id),
            )
            .join(Period, JeLine.period_id == Period.id)
            .where(JeLine.is_aasb16.is_(True))
            .group_by(Period.fy_year, Period.fy_month)
            .order_by(Period.fy_year, Period.fy_month)
        )
        aasb16_rows = result.all()

        if aasb16_rows:
            print(f"  {'FY':>6} {'Month':>6} {'AASB16 lines':>14}")
            print("  " + "-" * 30)
            for fy_year, fy_month, count in aasb16_rows:
                flag = "" if fy_month == 12 else "  *** UNEXPECTED"
                print(f"  FY{fy_year:>4} M{fy_month:02d}    {count:>10}{flag}")
        else:
            print("  No AASB16 lines found in any period")

        total_aasb16 = await db.execute(
            select(func.count(JeLine.id)).where(JeLine.is_aasb16.is_(True))
        )
        print(f"\n  Total is_aasb16=true rows: {total_aasb16.scalar()}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run())
