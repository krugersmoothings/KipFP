"""Consolidate all FY2024 periods and verify MC inclusion + IC elimination.

Run from the backend container:
    python -m scripts.consolidate_verify_fy2024
"""

import asyncio
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.account import Account
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.sync import JeLine
from app.services.consolidation_engine import consolidate_period


async def run():
    # ── 1. Consolidate all 12 periods ─────────────────────────────────────
    print("=" * 60)
    print("STEP 1: Running consolidation for FY2024 M01-M12")
    print("=" * 60)

    for fy_month in range(1, 13):
        print(f"\n--- Consolidating FY2024 M{fy_month:02d} ---")
        try:
            run_id = await consolidate_period(2024, fy_month)
            async with async_session_factory() as db:
                run = await db.get(ConsolidationRun, run_id)
                status = run.status.value if run else "unknown"
                balanced = run.bs_balanced if run else None
                ic = run.ic_alerts if run else None
                print(f"  Status: {status}, BS balanced: {balanced}")
                if ic:
                    print(f"  IC alerts: {ic}")
        except Exception as exc:
            print(f"  FAILED: {exc}")

    # ── 2. Verify MC rows in je_lines ─────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: Verifying MC je_lines exist for all FY2024 periods")
    print("=" * 60)

    async with async_session_factory() as db:
        result = await db.execute(select(Entity).where(Entity.code == "MC"))
        mc = result.scalar_one()

        result = await db.execute(
            select(
                Period.fy_month,
                func.count(JeLine.id),
            )
            .join(Period, JeLine.period_id == Period.id)
            .where(JeLine.entity_id == mc.id, Period.fy_year == 2024)
            .group_by(Period.fy_month)
            .order_by(Period.fy_month)
        )
        for fy_month, count in result.all():
            print(f"  M{fy_month:02d}: {count} je_lines")

    # ── 3. Verify MC revenue in consolidated P&L ──────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3: Consolidated P&L — MC revenue (REV-SALES) by month")
    print("=" * 60)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Account).where(Account.code == "REV-SALES")
        )
        rev_sales = result.scalar_one_or_none()

        if rev_sales is None:
            print("  ERROR: REV-SALES account not found")
            return

        for fy_month in range(1, 13):
            result = await db.execute(
                select(Period).where(
                    Period.fy_year == 2024, Period.fy_month == fy_month
                )
            )
            period = result.scalar_one()

            # MC entity-level
            result = await db.execute(
                select(ConsolidatedActual).where(
                    ConsolidatedActual.period_id == period.id,
                    ConsolidatedActual.account_id == rev_sales.id,
                    ConsolidatedActual.entity_id == mc.id,
                )
            )
            mc_actual = result.scalar_one_or_none()
            mc_amt = mc_actual.amount if mc_actual else 0

            # Group total
            result = await db.execute(
                select(ConsolidatedActual).where(
                    ConsolidatedActual.period_id == period.id,
                    ConsolidatedActual.account_id == rev_sales.id,
                    ConsolidatedActual.is_group_total.is_(True),
                )
            )
            group_actual = result.scalar_one_or_none()
            group_amt = group_actual.amount if group_actual else 0

            print(f"  M{fy_month:02d}: MC={mc_amt:>12,.2f}   Group={group_amt:>14,.2f}")

    # ── 4. IC elimination check — MC Sales vs SH 62300 ────────────────────
    print("\n" + "=" * 60)
    print("STEP 4: IC elimination — MC Sales (mapped *-1) vs SH 62300")
    print("=" * 60)

    async with async_session_factory() as db:
        result = await db.execute(select(Entity).where(Entity.code == "SH"))
        sh = result.scalar_one_or_none()

        for fy_month in range(1, 13):
            result = await db.execute(
                select(Period).where(
                    Period.fy_year == 2024, Period.fy_month == fy_month
                )
            )
            period = result.scalar_one()

            # MC Sales raw
            result = await db.execute(
                select(JeLine.amount).where(
                    JeLine.entity_id == mc.id,
                    JeLine.period_id == period.id,
                    JeLine.source_account_code == "Sales",
                )
            )
            mc_sales_raw = result.scalar_one_or_none() or Decimal("0")

            # SH 62300 raw
            sh_62300_raw = Decimal("0")
            if sh:
                result = await db.execute(
                    select(JeLine.amount).where(
                        JeLine.entity_id == sh.id,
                        JeLine.period_id == period.id,
                        JeLine.source_account_code == "62300",
                    )
                )
                val = result.scalar_one_or_none()
                if val is not None:
                    sh_62300_raw = Decimal(str(val))

            mc_mapped = Decimal(str(mc_sales_raw)) * Decimal("-1")
            net = mc_mapped + sh_62300_raw
            flag = " *** IMBALANCE" if abs(net) > 10 else ""
            print(
                f"  M{fy_month:02d}: MC Sales raw={mc_sales_raw:>12,.2f}  "
                f"mapped(*-1)={mc_mapped:>12,.2f}  "
                f"SH 62300={sh_62300_raw:>12,.2f}  "
                f"net={net:>10,.2f}{flag}"
            )


if __name__ == "__main__":
    asyncio.run(run())
