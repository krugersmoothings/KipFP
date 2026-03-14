"""Full batch sync: all active NetSuite entities x 12 FY2024 periods,
then consolidate, verify revenue, and diagnose mapping gaps.

Run from the backend container:
    python -m scripts.sync_all_netsuite_fy2024
"""

import asyncio
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func, literal_column
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine
from app.services.netsuite_sync_service import sync_entity
from app.services.consolidation_engine import consolidate_period


MONTH_LABELS = [
    "Jul-23", "Aug-23", "Sep-23", "Oct-23", "Nov-23", "Dec-23",
    "Jan-24", "Feb-24", "Mar-24", "Apr-24", "May-24", "Jun-24",
]


async def run():
    # ── 1. Look up all active NetSuite entities ──────────────────────────
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

    # ── 2. Sync all 12 months for every entity ───────────────────────────
    print("\n" + "=" * 70)
    print("STEP 1: Syncing all NetSuite entities for FY2024 M01-M12")
    print("=" * 70)

    total_syncs = 0
    failed_syncs = []

    for ent in entities:
        print(f"\n>>> {ent.code} ({ent.name})")
        for fy_month in range(1, 13):
            print(f"  M{fy_month:02d} ... ", end="", flush=True)
            try:
                run_id = await sync_entity(
                    entity_id=str(ent.id),
                    fy_year=2024,
                    fy_month=fy_month,
                )
                total_syncs += 1
                print("OK")
            except Exception as exc:
                failed_syncs.append((ent.code, fy_month, str(exc)))
                print(f"FAILED: {exc}")

    print(f"\nSync complete: {total_syncs} succeeded, {len(failed_syncs)} failed")
    if failed_syncs:
        print("Failures:")
        for code, month, err in failed_syncs:
            print(f"  {code} M{month:02d}: {err[:120]}")

    # ── 3. Verify je_lines coverage ──────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 2: je_lines coverage per entity per month")
    print("=" * 70)

    async with async_session_factory() as db:
        header = f"{'Entity':>6}"
        for m in range(1, 13):
            header += f"  M{m:02d}"
        print(header)
        print("-" * len(header))

        for ent in entities:
            result = await db.execute(
                select(Period.fy_month, func.count(JeLine.id))
                .join(Period, JeLine.period_id == Period.id)
                .where(JeLine.entity_id == ent.id, Period.fy_year == 2024)
                .group_by(Period.fy_month)
                .order_by(Period.fy_month)
            )
            counts = dict(result.all())
            line = f"{ent.code:>6}"
            for m in range(1, 13):
                c = counts.get(m, 0)
                line += f"  {c:>3}" if c else "    -"
            total = sum(counts.values())
            months_with_data = len(counts)
            line += f"  ({months_with_data}/12, {total} total)"
            print(line)

    # ── 4. Consolidate all 12 periods ────────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 3: Consolidating FY2024 M01-M12")
    print("=" * 70)

    for fy_month in range(1, 13):
        print(f"  M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(2024, fy_month)
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

    # ── 5. Verify consolidated revenue by month ──────────────────────────
    print("\n" + "=" * 70)
    print("STEP 4: Consolidated REV-SALES group total by month")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Account).where(Account.code == "REV-SALES")
        )
        rev = result.scalar_one()

        print(f"  {'Month':<8} {'Revenue':>14}  {'In Range?':>10}")
        print("  " + "-" * 36)

        for fy_month in range(1, 13):
            result = await db.execute(
                select(Period).where(
                    Period.fy_year == 2024, Period.fy_month == fy_month
                )
            )
            period = result.scalar_one_or_none()
            if not period:
                print(f"  M{fy_month:02d}      — no period")
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
            in_range = 1_750_000 <= abs_amt <= 2_950_000
            label = MONTH_LABELS[fy_month - 1]
            flag = "OK" if in_range else f"*** {'LOW' if abs_amt < 1_750_000 else 'HIGH'}"
            print(f"  M{fy_month:02d} {label}  {amt:>14,.2f}  {flag:>10}")

    # ── 6. Investigate SH 62300 IC issue ─────────────────────────────────
    print("\n" + "=" * 70)
    print("STEP 5: SH account 62300 — raw je_lines vs mapping")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(select(Entity).where(Entity.code == "SH"))
        sh = result.scalar_one_or_none()

        if sh:
            # Check je_lines for 62300
            result = await db.execute(
                select(
                    Period.fy_month,
                    JeLine.source_account_code,
                    JeLine.source_account_name,
                    JeLine.amount,
                )
                .join(Period, JeLine.period_id == Period.id)
                .where(
                    JeLine.entity_id == sh.id,
                    Period.fy_year == 2024,
                    JeLine.source_account_code == "62300",
                )
                .order_by(Period.fy_month)
            )
            rows = result.all()
            if rows:
                print(f"  SH je_lines with source_account_code='62300': {len(rows)} rows")
                for fy_month, code, name, amt in rows:
                    print(f"    M{fy_month:02d}: {code} '{name}' amount={amt}")
            else:
                print("  No je_lines found for SH account 62300")
                # Check what account codes SH DOES have that are close
                result = await db.execute(
                    select(JeLine.source_account_code, JeLine.source_account_name)
                    .join(Period, JeLine.period_id == Period.id)
                    .where(
                        JeLine.entity_id == sh.id,
                        Period.fy_year == 2024,
                        JeLine.source_account_code.like("623%"),
                    )
                    .distinct()
                )
                similar = result.all()
                if similar:
                    print("  Similar account codes found:")
                    for code, name in similar:
                        print(f"    {code}: {name}")
                else:
                    print("  No account codes starting with 623 found for SH")

                # Check if any SH entity has 62300 in the mapping
                result = await db.execute(
                    select(AccountMapping)
                    .where(
                        AccountMapping.entity_id == sh.id,
                        AccountMapping.source_account_code == "62300",
                    )
                )
                mapping = result.scalar_one_or_none()
                if mapping:
                    print(f"  Mapping exists: 62300 -> account_id={mapping.target_account_id}, multiplier={mapping.multiplier}")
                else:
                    print("  No mapping found for SH 62300")
        else:
            print("  SH entity not found")

    # ── 7. List unmapped je_lines by account code ────────────────────────
    print("\n" + "=" * 70)
    print("STEP 6: Unmapped je_lines — account codes without COA mappings")
    print("=" * 70)

    async with async_session_factory() as db:
        # For each NetSuite entity, find je_lines whose source_account_code
        # has no matching AccountMapping row
        all_unmapped: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        unmapped_names: dict[str, str] = {}

        for ent in entities:
            # Get all mapped source codes for this entity
            result = await db.execute(
                select(AccountMapping.source_account_code)
                .where(AccountMapping.entity_id == ent.id)
            )
            mapped_codes = {r[0] for r in result.all()}

            # Get all je_line source codes for this entity in FY2024
            result = await db.execute(
                select(
                    JeLine.source_account_code,
                    JeLine.source_account_name,
                    func.sum(JeLine.amount),
                    func.count(JeLine.id),
                )
                .join(Period, JeLine.period_id == Period.id)
                .where(JeLine.entity_id == ent.id, Period.fy_year == 2024)
                .group_by(JeLine.source_account_code, JeLine.source_account_name)
            )
            for code, name, total, count in result.all():
                if code not in mapped_codes:
                    key = f"{ent.code}:{code}"
                    all_unmapped[key]["total"] += Decimal(str(total))
                    all_unmapped[key]["count"] += count
                    unmapped_names[key] = name or ""

        if all_unmapped:
            # Sort by absolute total amount descending
            sorted_items = sorted(
                all_unmapped.items(),
                key=lambda x: abs(x[1]["total"]),
                reverse=True,
            )
            print(f"\n  {'Entity:Code':<25} {'Name':<40} {'Lines':>6} {'Total Amount':>16}")
            print("  " + "-" * 91)
            for key, data in sorted_items[:40]:
                name = unmapped_names.get(key, "")[:38]
                print(f"  {key:<25} {name:<40} {int(data['count']):>6} {float(data['total']):>16,.2f}")
            if len(sorted_items) > 40:
                print(f"  ... and {len(sorted_items) - 40} more")
            print(f"\n  Total unmapped combinations: {len(sorted_items)}")
        else:
            print("  No unmapped je_lines found!")

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run())
