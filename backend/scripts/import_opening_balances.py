"""Import opening balances for all active entities at the start of FY2025
(i.e. cumulative TB as at June 30, 2024), then consolidate month-0.

This populates the ``fy_month=0`` period with cumulative balances from the
source systems, enabling the balance sheet to show correct point-in-time
balances instead of just monthly movements.

Run from the backend directory:
    python -m scripts.import_opening_balances
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity, SourceSystem
from app.db.models.period import Period
from app.db.models.sync import JeLine
from app.services.opening_balance_service import sync_opening_balance
from app.services.consolidation_engine import consolidate_period

FY_YEAR = 2025


async def run():
    print("=" * 70)
    print(f"Opening-balance import for FY{FY_YEAR} (as at 30-Jun-{FY_YEAR - 1})")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity).where(Entity.is_active.is_(True)).order_by(Entity.code)
        )
        entities = list(result.scalars().all())

    print(f"\nFound {len(entities)} active entities\n")

    for entity in entities:
        src = entity.source_system.value if entity.source_system else "?"
        print(f"  {entity.code:6s} ({src:8s}) ... ", end="", flush=True)
        try:
            run_id = await sync_opening_balance(entity.id, FY_YEAR)
            async with async_session_factory() as db:
                count = await db.execute(
                    select(func.count())
                    .select_from(JeLine)
                    .where(
                        JeLine.entity_id == entity.id,
                        JeLine.sync_run_id == run_id,
                    )
                )
                n = count.scalar()
            print(f"OK  ({n} rows)")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # Consolidate the opening-balance period
    print("\n" + "=" * 70)
    print(f"Consolidating FY{FY_YEAR} M00 (opening balances)")
    print("=" * 70)

    try:
        crun_id = await consolidate_period(FY_YEAR, 0)
        async with async_session_factory() as db:
            crun = await db.get(ConsolidationRun, crun_id)
            if crun:
                print(f"  Status: {crun.status.value}")
                print(f"  BS balanced: {crun.bs_balanced}")
                print(f"  BS variance: {crun.bs_variance}")
            else:
                print(f"  Run id: {crun_id}")
    except Exception as exc:
        print(f"  FAILED: {exc}")

    # Verify: show a few key BS accounts
    print("\n" + "=" * 70)
    print("Verification — key BS balances (group total)")
    print("=" * 70)

    async with async_session_factory() as db:
        from app.db.models.account import Account
        result = await db.execute(
            select(Period).where(
                Period.fy_year == FY_YEAR, Period.fy_month == 0
            )
        )
        ob_period = result.scalar_one_or_none()
        if ob_period is None:
            print("  No opening-balance period found")
            return

        key_codes = [
            "BS-TOTALCURRENT", "BS-TOTALNONCURRENT", "BS-TOTALASSETS",
            "BS-TOTALCURRENTLIAB", "BS-TOTALNONCURRENTLIAB", "BS-TOTALLIAB",
            "BS-TOTALEQUITY",
        ]
        for code in key_codes:
            result = await db.execute(
                select(Account).where(Account.code == code)
            )
            acct = result.scalar_one_or_none()
            if acct is None:
                continue
            result = await db.execute(
                select(func.coalesce(func.sum(ConsolidatedActual.amount), 0))
                .where(
                    ConsolidatedActual.period_id == ob_period.id,
                    ConsolidatedActual.account_id == acct.id,
                    ConsolidatedActual.is_group_total.is_(True),
                )
            )
            amt = float(result.scalar())
            sign = -1.0 if acct.normal_balance and acct.normal_balance.value == "credit" else 1.0
            display = amt * sign
            print(f"  {code:30s} {display:>14,.0f}")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(run())
