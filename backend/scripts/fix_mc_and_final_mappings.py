"""Map remaining MC (Xero) accounts + NAR:25302, re-consolidate, check BS.

Run from the backend container:
    python -m scripts.fix_mc_and_final_mappings
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.entity import Entity
from app.db.models.consolidation import ConsolidationRun
from app.services.consolidation_engine import consolidate_period

MC_EFFECTIVE = date(2020, 1, 1)
NS_EFFECTIVE = date(2021, 7, 1)

MC_MAPPINGS: dict[str, str] = {
    # BS — assets
    "Accounts Receivable":      "BS-DEBTORS",
    "Cash in Hand":             "BS-CASH",
    "Client Integrated Account":"BS-CASH",
    "Computer Equipment":       "BS-PPE",
    "Less Accumulated Depreciation on Computer Equipment": "BS-PPE",
    # BS — liabilities
    "GST":                      "BS-GST",
    "Income Tax Payable":       "BS-TAX-PAYABLE",
    "Other Creditors":          "BS-CREDITORS",
    "PAYG Withholdings Payable":"BS-EMPLOYPAYABLES",
    "Superannuation Payable":   "BS-EMPLOYPAYABLES",
    "Wages Payable - Payroll":  "BS-EMPLOYPAYABLES",
    "Loan":                     "BS-OTHERCURRENTLIAB",
    "Loan - Grey Chimp Investment Trust":  "BS-OTHERCURRENTLIAB",
    "Loan - Pink Panda Investment Trust":  "BS-OTHERCURRENTLIAB",
    "Suspense":                 "BS-OTHERCURRENTLIAB",
    # BS — equity
    "Retained Earnings":        "BS-RETAINEDEARNINGS",
    "Owner A Share Capital":    "BS-RETAINEDEARNINGS",
    "Modulus Capital":          "BS-RETAINEDEARNINGS",
    "MODULUS SL":               "BS-RETAINEDEARNINGS",
    "MODULUS WR":               "BS-RETAINEDEARNINGS",
    "Dividends Paid - Franked": "BS-RETAINEDEARNINGS",
    "Dividends Paid Franked - TO SL": "BS-RETAINEDEARNINGS",
    "Dividends paid franked - TO WR": "BS-RETAINEDEARNINGS",
    "Capital Loss Reserve":     "BS-RETAINEDEARNINGS",
    # IS — tax
    "Over/(Under) Provision of Tax": "TAX",
}


async def run():
    async with async_session_factory() as db:
        result = await db.execute(select(Account))
        acct_by_code = {a.code: a for a in result.scalars().all()}

        # MC entity
        result = await db.execute(select(Entity).where(Entity.code == "MC"))
        mc = result.scalar_one_or_none()
        if not mc:
            print("ERROR: MC entity not found")
            return

        # NAR entity
        result = await db.execute(select(Entity).where(Entity.code == "NAR"))
        nar = result.scalar_one_or_none()

        added = 0

        # MC mappings
        for src, tgt_code in MC_MAPPINGS.items():
            tgt = acct_by_code.get(tgt_code)
            if not tgt:
                print(f"  WARNING: {tgt_code} not found for '{src}'")
                continue
            result = await db.execute(
                select(AccountMapping).where(
                    AccountMapping.entity_id == mc.id,
                    AccountMapping.source_account_code == src,
                )
            )
            if result.scalar_one_or_none():
                continue
            db.add(AccountMapping(
                entity_id=mc.id,
                source_account_code=src,
                target_account_id=tgt.id,
                multiplier=1.0,
                effective_from=MC_EFFECTIVE,
            ))
            added += 1

        # NAR:25302
        if nar:
            tgt = acct_by_code.get("BS-OTHERCURRENTLIAB")
            if tgt:
                result = await db.execute(
                    select(AccountMapping).where(
                        AccountMapping.entity_id == nar.id,
                        AccountMapping.source_account_code == "25302",
                    )
                )
                if not result.scalar_one_or_none():
                    db.add(AccountMapping(
                        entity_id=nar.id,
                        source_account_code="25302",
                        target_account_id=tgt.id,
                        multiplier=1.0,
                        effective_from=NS_EFFECTIVE,
                    ))
                    added += 1

        print(f"Added {added} mappings")
        await db.commit()

    # Re-consolidate
    print("\nRe-consolidating FY2024 M01-M12...")
    results = []
    for m in range(1, 13):
        print(f"  M{m:02d} ... ", end="", flush=True)
        try:
            rid = await consolidate_period(2024, m)
            async with async_session_factory() as db:
                cr = await db.get(ConsolidationRun, rid)
                b = cr.bs_balanced if cr else None
                v = cr.bs_variance if cr else None
                results.append((m, b, v))
                print(f"balanced={b}, variance={v}")
        except Exception as e:
            results.append((m, None, None))
            print(f"FAILED: {e}")

    print(f"\n{'Month':<8} {'Balanced':>10} {'Variance':>14}")
    print("-" * 34)
    ok = 0
    for m, b, v in results:
        vs = f"{float(v):>14,.2f}" if v is not None else "           N/A"
        print(f"M{m:02d}      {'YES' if b else 'NO':>10} {vs}")
        if b:
            ok += 1
    print(f"\n{ok}/12 months balanced")


if __name__ == "__main__":
    asyncio.run(run())
