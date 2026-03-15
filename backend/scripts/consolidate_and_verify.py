"""Re-consolidate FY2025 M01-12 + FY2026 M01-07 and verify revenue.

Run from the backend container:
    python -m scripts.consolidate_and_verify
"""

import asyncio
import sys
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine
from app.services.consolidation_engine import consolidate_period

SYNC_RANGES: list[tuple[int, range]] = [
    (2025, range(1, 13)),
    (2026, range(1, 8)),
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
    print("=" * 70)
    print("STEP 1: Consolidating all 19 periods")
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

    print("\n" + "=" * 70)
    print("STEP 2: Consolidated REV-SALES group total by month")
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

    # Check for unmapped accounts
    print("\n" + "=" * 70)
    print("STEP 3: Unmapped accounts check")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity)
            .where(Entity.is_active.is_(True), Entity.source_system == "netsuite")
            .order_by(Entity.code)
        )
        entities = list(result.scalars().all())

        all_unmapped: dict[str, dict[str, Decimal]] = defaultdict(lambda: defaultdict(Decimal))
        unmapped_names: dict[str, str] = {}

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

    print("\n" + "=" * 70)
    print("DONE")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(run())
