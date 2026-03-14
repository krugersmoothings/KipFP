"""Add missing COA accounts + mappings for unmapped je_lines,
then re-consolidate FY2024 and check BS balance.

Run from the backend container:
    python -m scripts.fix_unmapped_accounts
"""

import asyncio
import sys
import uuid
from datetime import date
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.base import async_session_factory
from app.db.models.account import (
    Account,
    AccountMapping,
    AccountType,
    NormalBalance,
    Statement,
)
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.services.consolidation_engine import consolidate_period

DEFAULT_EFFECTIVE = date(2021, 7, 1)


async def run():
    async with async_session_factory() as db:

        # ── Load existing accounts by code ───────────────────────────────
        result = await db.execute(select(Account))
        acct_by_code: dict[str, Account] = {a.code: a for a in result.scalars().all()}

        # ── Load all active NetSuite entities ────────────────────────────
        result = await db.execute(
            select(Entity)
            .where(Entity.is_active.is_(True), Entity.source_system == "netsuite")
            .order_by(Entity.code)
        )
        ns_entities = list(result.scalars().all())
        print(f"NetSuite entities: {[e.code for e in ns_entities]}")

        # Also load SH specifically
        sh = next((e for e in ns_entities if e.code == "SH"), None)

        # ── 1. Create OPEX-GAINLOSS IS account ──────────────────────────
        changes = 0

        if "OPEX-GAINLOSS" not in acct_by_code:
            acct_id = uuid.uuid4()
            acct = Account(
                id=acct_id,
                code="OPEX-GAINLOSS",
                name="Gain/(Loss) on Asset Sale",
                account_type=AccountType.income,
                statement=Statement.is_,
                sort_order=295,
                is_subtotal=False,
                normal_balance=NormalBalance.credit,
            )
            db.add(acct)
            acct_by_code["OPEX-GAINLOSS"] = acct
            print("Created: OPEX-GAINLOSS (IS, sort_order=295)")
            changes += 1
        else:
            print("OPEX-GAINLOSS already exists")

        # ── 2. Create BS-DEBT-11526 BS account ──────────────────────────
        if "BS-DEBT-11526" not in acct_by_code:
            acct_id = uuid.uuid4()
            acct = Account(
                id=acct_id,
                code="BS-DEBT-11526",
                name="Debt Facility 11526 (Cambridge)",
                account_type=AccountType.liability,
                statement=Statement.bs,
                sort_order=2245,
                is_subtotal=False,
                normal_balance=NormalBalance.credit,
            )
            db.add(acct)
            acct_by_code["BS-DEBT-11526"] = acct
            print("Created: BS-DEBT-11526 (BS, sort_order=2245)")
            changes += 1
        else:
            print("BS-DEBT-11526 already exists")

        await db.flush()

        # ── 3. Update EBIT formula to include OPEX-GAINLOSS ─────────────
        ebit = acct_by_code.get("EBIT")
        if ebit and ebit.subtotal_formula:
            formula = ebit.subtotal_formula
            add_codes = formula.get("add", [])
            if "OPEX-GAINLOSS" not in add_codes:
                add_codes.append("OPEX-GAINLOSS")
                ebit.subtotal_formula = {**formula, "add": add_codes}
                print(f"Updated EBIT formula: {ebit.subtotal_formula}")
                changes += 1
            else:
                print("EBIT formula already includes OPEX-GAINLOSS")

        # ── 4. Update BS-TOTALDEBT formula to include BS-DEBT-11526 ──────
        total_debt = acct_by_code.get("BS-TOTALDEBT")
        if total_debt and total_debt.subtotal_formula:
            formula = total_debt.subtotal_formula
            add_codes = formula.get("add", [])
            if "BS-DEBT-11526" not in add_codes:
                add_codes.append("BS-DEBT-11526")
                total_debt.subtotal_formula = {**formula, "add": add_codes}
                print(f"Updated BS-TOTALDEBT formula: {total_debt.subtotal_formula}")
                changes += 1
            else:
                print("BS-TOTALDEBT formula already includes BS-DEBT-11526")

        await db.flush()

        # ── 5. Add account mappings ──────────────────────────────────────
        GLOBAL_MAPPINGS = [
            ("18100", "BS-PPE"),
            ("18800", "BS-PPE"),
            ("19110", "BS-INTANGIBLES"),
            ("29400", "BS-PROVISIONS"),
            ("44000", "OPEX-GAINLOSS"),
        ]

        mappings_added = 0
        mappings_skipped = 0

        for ent in ns_entities:
            effective = ent.acquisition_date or DEFAULT_EFFECTIVE
            for src_code, tgt_code in GLOBAL_MAPPINGS:
                tgt_acct = acct_by_code.get(tgt_code)
                if tgt_acct is None:
                    print(f"  WARNING: target account {tgt_code} not found")
                    continue

                # Check if mapping already exists
                result = await db.execute(
                    select(AccountMapping).where(
                        AccountMapping.entity_id == ent.id,
                        AccountMapping.source_account_code == src_code,
                    )
                )
                existing = result.scalar_one_or_none()
                if existing:
                    mappings_skipped += 1
                    continue

                db.add(AccountMapping(
                    entity_id=ent.id,
                    source_account_code=src_code,
                    target_account_id=tgt_acct.id,
                    multiplier=1.0,
                    effective_from=effective,
                ))
                mappings_added += 1

        # SH-specific mapping: 11526 → BS-DEBT-11526
        if sh:
            tgt_acct = acct_by_code.get("BS-DEBT-11526")
            if tgt_acct:
                result = await db.execute(
                    select(AccountMapping).where(
                        AccountMapping.entity_id == sh.id,
                        AccountMapping.source_account_code == "11526",
                    )
                )
                existing = result.scalar_one_or_none()
                if not existing:
                    db.add(AccountMapping(
                        entity_id=sh.id,
                        source_account_code="11526",
                        target_account_id=tgt_acct.id,
                        multiplier=1.0,
                        effective_from=sh.acquisition_date or DEFAULT_EFFECTIVE,
                    ))
                    mappings_added += 1
                    print(f"Added SH:11526 → BS-DEBT-11526")
                else:
                    mappings_skipped += 1

        print(f"\nMappings: {mappings_added} added, {mappings_skipped} already existed")
        await db.commit()

    # ── 6. Re-consolidate all 12 FY2024 periods ─────────────────────────
    print("\n" + "=" * 60)
    print("Re-consolidating FY2024 M01-M12")
    print("=" * 60)

    results = []
    for fy_month in range(1, 13):
        print(f"  M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(2024, fy_month)
            async with async_session_factory() as db:
                crun = await db.get(ConsolidationRun, run_id)
                balanced = crun.bs_balanced if crun else None
                variance = crun.bs_variance if crun else None
                unmapped_note = ""
                results.append((fy_month, balanced, variance))
                print(f"BS balanced={balanced}, variance={variance}")
        except Exception as exc:
            results.append((fy_month, None, None))
            print(f"FAILED: {exc}")

    # ── 7. Summary ───────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("BS Balance Summary")
    print("=" * 60)
    print(f"  {'Month':<8} {'Balanced':>10} {'Variance':>14}")
    print("  " + "-" * 34)

    balanced_count = 0
    for fy_month, balanced, variance in results:
        var_str = f"{float(variance):>14,.2f}" if variance is not None else "         N/A"
        bal_str = "YES" if balanced else "NO"
        print(f"  M{fy_month:02d}      {bal_str:>10} {var_str}")
        if balanced:
            balanced_count += 1

    print(f"\n  {balanced_count}/12 months balanced")

    if balanced_count < 12:
        print("\n  Remaining unmapped accounts are likely causing the imbalance.")
        print("  See the previous sync_all_netsuite_fy2024 output for the full list.")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(run())
