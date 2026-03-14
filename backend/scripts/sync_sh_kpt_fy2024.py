"""Sync SH and KPT (NetSuite) for all 12 FY2024 periods,
then consolidate and verify je_lines coverage + P&L totals.

Run from the backend directory:
    python -m scripts.sync_sh_kpt_fy2024
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
from app.db.models.account import Account
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.services.netsuite_sync_service import sync_entity
from app.services.consolidation_engine import consolidate_period


async def run():
    # ── 1. Look up entities ──────────────────────────────────────────────
    async with async_session_factory() as db:
        result = await db.execute(
            select(Entity).where(Entity.code.in_(["SH", "KPT"]))
        )
        entities = {e.code: e for e in result.scalars().all()}

    for code in ("SH", "KPT"):
        if code not in entities:
            print(f"ERROR: {code} entity not found")
            return
        ent = entities[code]
        print(f"{code}: {ent.id} — {ent.name} (source={ent.source_system})")

    # ── 2. Sync all 12 months for both entities ──────────────────────────
    print("\n" + "=" * 60)
    print("STEP 1: Syncing SH + KPT for FY2024 M01-M12")
    print("=" * 60)

    for code in ("SH", "KPT"):
        ent = entities[code]
        print(f"\n>>> {code}")
        for fy_month in range(1, 13):
            print(f"  M{fy_month:02d} ... ", end="", flush=True)
            try:
                run_id = await sync_entity(
                    entity_id=str(ent.id),
                    fy_year=2024,
                    fy_month=fy_month,
                )
                print(f"OK (run {run_id})")
            except Exception as exc:
                print(f"FAILED: {exc}")

    # ── 3. Verify je_lines coverage ──────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 2: Verifying je_lines for SH + KPT across all FY2024 months")
    print("=" * 60)

    async with async_session_factory() as db:
        for code in ("SH", "KPT"):
            ent = entities[code]
            result = await db.execute(
                select(
                    Period.fy_month,
                    func.count(JeLine.id),
                    func.sum(JeLine.amount),
                )
                .join(Period, JeLine.period_id == Period.id)
                .where(JeLine.entity_id == ent.id, Period.fy_year == 2024)
                .group_by(Period.fy_month)
                .order_by(Period.fy_month)
            )
            rows = result.all()
            print(f"\n  {code} ({len(rows)}/12 months with data):")
            for fy_month, count, total_amt in rows:
                print(f"    M{fy_month:02d}: {count:>4} lines, total={total_amt:>14,.2f}")

            if len(rows) < 12:
                missing = set(range(1, 13)) - {r[0] for r in rows}
                print(f"    *** MISSING months: {sorted(missing)}")

    # ── 4. Consolidate all 12 periods ────────────────────────────────────
    print("\n" + "=" * 60)
    print("STEP 3: Consolidating FY2024 M01-M12")
    print("=" * 60)

    for fy_month in range(1, 13):
        print(f"  M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(2024, fy_month)
            async with async_session_factory() as db:
                crun = await db.get(ConsolidationRun, run_id)
                status = crun.status.value if crun else "?"
                balanced = crun.bs_balanced if crun else None
                print(f"OK ({status}, BS balanced={balanced})")
                if crun and crun.ic_alerts:
                    print(f"       IC alerts: {crun.ic_alerts}")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # ── 5. Verify consolidated P&L — REV-SALES by entity by month ────────
    print("\n" + "=" * 60)
    print("STEP 4: Consolidated REV-SALES by entity by month")
    print("=" * 60)

    async with async_session_factory() as db:
        result = await db.execute(
            select(Account).where(Account.code == "REV-SALES")
        )
        rev = result.scalar_one_or_none()
        if rev is None:
            print("  ERROR: REV-SALES not found")
            return

        all_entities = await db.execute(
            select(Entity).where(Entity.is_active.is_(True)).order_by(Entity.code)
        )
        ents = list(all_entities.scalars().all())
        ent_codes = [e.code for e in ents]
        header = "  Month  " + "".join(f"{c:>14}" for c in ent_codes) + "       Group"
        print(header)
        print("  " + "-" * (len(header) - 2))

        for fy_month in range(1, 13):
            result = await db.execute(
                select(Period).where(
                    Period.fy_year == 2024, Period.fy_month == fy_month
                )
            )
            period = result.scalar_one_or_none()
            if period is None:
                print(f"  M{fy_month:02d}  — period not found")
                continue

            line = f"  M{fy_month:02d}  "
            for ent in ents:
                result = await db.execute(
                    select(func.coalesce(func.sum(ConsolidatedActual.amount), 0)).where(
                        ConsolidatedActual.period_id == period.id,
                        ConsolidatedActual.account_id == rev.id,
                        ConsolidatedActual.entity_id == ent.id,
                    )
                )
                amt = float(result.scalar())
                line += f"{amt:>14,.2f}"

            result = await db.execute(
                select(func.coalesce(func.sum(ConsolidatedActual.amount), 0)).where(
                    ConsolidatedActual.period_id == period.id,
                    ConsolidatedActual.account_id == rev.id,
                    ConsolidatedActual.is_group_total.is_(True),
                )
            )
            group = float(result.scalar())
            line += f"{group:>14,.2f}"
            print(line)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(run())
