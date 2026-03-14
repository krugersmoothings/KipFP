"""Batch sync: all active NetSuite entities for FY2025 (M01-12) + FY2026 (M01-07),
then detect/auto-map unmapped accounts, consolidate, and verify revenue.

Run from the backend container:
    python -m scripts.sync_fy2025_fy2026
"""

import asyncio
import sys
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine, SyncRun, SyncStatus
from app.services.netsuite_sync_service import sync_entity
from app.services.consolidation_engine import consolidate_period

SYNC_RANGES: list[tuple[int, range]] = [
    (2025, range(1, 13)),   # FY2025 M01-M12 = Jul 2024 – Jun 2025
    (2026, range(1, 8)),    # FY2026 M01-M07 = Jul 2025 – Jan 2026
]

ALL_PERIODS: list[tuple[int, int]] = []
for fy_year, months in SYNC_RANGES:
    for m in months:
        ALL_PERIODS.append((fy_year, m))

MONTH_ABBR = ["Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
              "Jan", "Feb", "Mar", "Apr", "May", "Jun"]


def _period_label(fy_year: int, fy_month: int) -> str:
    cal_year = fy_year - 1 if fy_month <= 6 else fy_year
    return f"{MONTH_ABBR[fy_month - 1]}-{cal_year % 100:02d}"


async def run():
    # ── 1. Sync all periods ──────────────────────────────────────────────
    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity)
            .where(Entity.is_active.is_(True), Entity.source_system == "netsuite")
            .order_by(Entity.code)
        )
        entities = list(result.scalars().all())

    print(f"Found {len(entities)} active NetSuite entities:")
    for e in entities:
        print(f"  {e.code:>5}  {e.id}  {e.name}")

    print("\n" + "=" * 70)
    print("STEP 1: Syncing all entities for FY2025 M01-12 + FY2026 M01-07")
    print(f"        {len(ALL_PERIODS)} periods x {len(entities)} entities = {len(ALL_PERIODS) * len(entities)} syncs")
    print("=" * 70)

    total_syncs = 0
    failed_syncs = []

    for ent in entities:
        print(f"\n>>> {ent.code} ({ent.name})")
        for fy_year, fy_month in ALL_PERIODS:
            label = _period_label(fy_year, fy_month)
            print(f"  FY{fy_year} M{fy_month:02d} ({label}) ... ", end="", flush=True)
            try:
                run_id = await sync_entity(
                    entity_id=str(ent.id),
                    fy_year=fy_year,
                    fy_month=fy_month,
                )
                async with async_session_factory() as check_db:
                    srun = await check_db.get(SyncRun, run_id)
                    if srun and srun.status == SyncStatus.failed:
                        err = (srun.error_detail or "unknown")[:120]
                        failed_syncs.append((ent.code, fy_year, fy_month, err))
                        print(f"FAILED: {err}")
                    else:
                        total_syncs += 1
                        recs = srun.records_upserted if srun else 0
                        print(f"OK ({recs} rows)")
            except Exception as exc:
                failed_syncs.append((ent.code, fy_year, fy_month, str(exc)))
                print(f"FAILED: {exc}")

    print(f"\nSync complete: {total_syncs} succeeded, {len(failed_syncs)} failed")
    if failed_syncs:
        print("Failures:")
        for code, fy, fm, err in failed_syncs:
            print(f"  {code} FY{fy} M{fm:02d}: {err[:120]}")

    # ── 2. Verify je_lines coverage ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 2: je_lines coverage per entity per period")
    print("=" * 70)

    async with async_session_factory() as db:
        for fy_year, months in SYNC_RANGES:
            month_list = list(months)
            header = f"{'Entity':>6}"
            for m in month_list:
                header += f"  M{m:02d}"
            print(f"\nFY{fy_year}:")
            print(header)
            print("-" * len(header))

            for ent in entities:
                result = await db.execute(
                    select(Period.fy_month, func.count(JeLine.id))
                    .join(Period, JeLine.period_id == Period.id)
                    .where(JeLine.entity_id == ent.id, Period.fy_year == fy_year)
                    .group_by(Period.fy_month)
                    .order_by(Period.fy_month)
                )
                counts = dict(result.all())
                line = f"{ent.code:>6}"
                for m in month_list:
                    c = counts.get(m, 0)
                    line += f"  {c:>3}" if c else "    -"
                total = sum(counts.get(m, 0) for m in month_list)
                line += f"  ({total} total)"
                print(line)

    # ── 3. Detect unmapped accounts ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 3: Detecting unmapped accounts in FY2025-FY2026 data")
    print("=" * 70)

    async with async_session_factory() as db:
        all_unmapped: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        unmapped_names: dict[str, str] = {}
        unmapped_entities: dict[str, tuple] = {}  # key -> (entity_id, source_code)

        for ent in entities:
            result = await db.execute(
                select(AccountMapping.source_account_code)
                .where(AccountMapping.entity_id == ent.id)
            )
            mapped_codes = {r[0] for r in result.all()}

            for fy_year, months in SYNC_RANGES:
                result = await db.execute(
                    select(
                        JeLine.source_account_code,
                        JeLine.source_account_name,
                        func.sum(JeLine.amount),
                        func.count(JeLine.id),
                    )
                    .join(Period, JeLine.period_id == Period.id)
                    .where(JeLine.entity_id == ent.id, Period.fy_year == fy_year)
                    .group_by(JeLine.source_account_code, JeLine.source_account_name)
                )
                for code, name, total, count in result.all():
                    if code not in mapped_codes:
                        key = f"{ent.code}:{code}"
                        all_unmapped[key]["total"] += Decimal(str(total))
                        all_unmapped[key]["count"] += count
                        unmapped_names[key] = name or ""
                        unmapped_entities[key] = (ent.id, code)

    if all_unmapped:
        sorted_items = sorted(
            all_unmapped.items(),
            key=lambda x: abs(x[1]["total"]),
            reverse=True,
        )
        print(f"\n  {'Entity:Code':<25} {'Name':<40} {'Lines':>6} {'Total Amount':>16}")
        print("  " + "-" * 91)
        for key, data in sorted_items[:60]:
            name = unmapped_names.get(key, "")[:38]
            print(f"  {key:<25} {name:<40} {int(data['count']):>6} {float(data['total']):>16,.2f}")
        if len(sorted_items) > 60:
            print(f"  ... and {len(sorted_items) - 60} more")
        print(f"\n  Total unmapped combinations: {len(sorted_items)}")
    else:
        print("  No unmapped je_lines found!")

    # ── 4. Auto-map using existing patterns ──────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 4: Auto-mapping using existing account code patterns")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(select(AccountMapping))
        existing_mappings = list(result.scalars().all())
        code_to_mapping: dict[str, AccountMapping] = {}
        for m in existing_mappings:
            code_to_mapping[m.source_account_code] = m

        result = await db.execute(select(Account))
        acct_by_code = {a.code: a for a in result.scalars().all()}

        auto_mapped = 0
        still_unmapped = []
        effective = date(2024, 7, 1)

        for key, (entity_id, src_code) in unmapped_entities.items():
            existing = code_to_mapping.get(src_code)
            if existing:
                result = await db.execute(
                    select(AccountMapping).where(
                        AccountMapping.entity_id == entity_id,
                        AccountMapping.source_account_code == src_code,
                    )
                )
                already = result.scalar_one_or_none()
                if already:
                    continue

                db.add(AccountMapping(
                    entity_id=entity_id,
                    source_account_code=src_code,
                    source_account_name=unmapped_names.get(key, ""),
                    target_account_id=existing.target_account_id,
                    multiplier=existing.multiplier,
                    effective_from=effective,
                    notes=f"Auto-mapped from {existing.entity_id} pattern",
                ))
                auto_mapped += 1
                tgt = next((a for a in acct_by_code.values() if a.id == existing.target_account_id), None)
                tgt_label = tgt.code if tgt else str(existing.target_account_id)
                print(f"  MAPPED {key:<25} -> {tgt_label} (multiplier={existing.multiplier})")
            else:
                still_unmapped.append(key)

        await db.commit()
        print(f"\n  Auto-mapped: {auto_mapped}")
        if still_unmapped:
            print(f"  Still unmapped ({len(still_unmapped)}):")
            for k in still_unmapped:
                name = unmapped_names.get(k, "")
                amt = float(all_unmapped[k]["total"])
                print(f"    {k:<25} {name:<40} {amt:>14,.2f}")

    # ── 5. Consolidate all periods ───────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 5: Consolidating all 19 periods")
    print("=" * 70)

    for fy_year, fy_month in ALL_PERIODS:
        label = _period_label(fy_year, fy_month)
        print(f"  FY{fy_year} M{fy_month:02d} ({label}) ... ", end="", flush=True)
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

    # ── 6. Verify consolidated revenue ───────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 6: Consolidated REV-SALES group total by month")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Account).where(Account.code == "REV-SALES")
        )
        rev = result.scalar_one_or_none()
        if not rev:
            print("  ERROR: REV-SALES account not found!")
            return

        print(f"  {'Period':<16} {'Revenue':>14}  {'In Range?':>10}")
        print("  " + "-" * 44)

        for fy_year, fy_month in ALL_PERIODS:
            label = _period_label(fy_year, fy_month)
            result = await db.execute(
                select(Period).where(
                    Period.fy_year == fy_year, Period.fy_month == fy_month
                )
            )
            period = result.scalar_one_or_none()
            if not period:
                print(f"  FY{fy_year} M{fy_month:02d} ({label})  — no period")
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
            flag = "OK" if in_range else f"*** {'LOW' if abs_amt < 1_750_000 else 'HIGH'}"
            print(f"  FY{fy_year} M{fy_month:02d} ({label})  {amt:>14,.2f}  {flag:>10}")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run())
