"""Map ALL remaining unmapped je_lines and re-consolidate.

Run from the backend container:
    python -m scripts.fix_remaining_unmapped
"""

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.entity import Entity
from app.db.models.consolidation import ConsolidationRun
from app.services.consolidation_engine import consolidate_period

DEFAULT_EFFECTIVE = date(2021, 7, 1)

# source_code → target COA code
# Applied to ALL NetSuite entities unless overridden below
GLOBAL_MAPPINGS: dict[str, str] = {
    # Fixed assets / ROU / accumulated depreciation
    "18960": "BS-ROU",          # Accum Amort ROU Asset under Lease
    "18500": "BS-ROU",          # Leasehold (ROU)
    "18400": "BS-PPE",          # Motor Vehicle
    "18200": "BS-PPE",          # Minor Equipment
    # Intangibles
    "19105": "BS-INTANGIBLES",  # Borrowing Costs Sinking fund
    "19140": "BS-INTANGIBLES",  # Capitalised Legal Fees
    "19001": "BS-DEFTAX",       # Deferred tax asset
    "19120": "BS-INTANGIBLES",  # Capitalised R&D
    "19145": "BS-INTANGIBLES",  # IP
    "19153": "BS-INTANGIBLES",  # Accum Trademark Amortisation
    # Non-current liabilities
    "29100": "BS-PROVISIONS",   # Deferred tax liability (closest existing)
    # Current liabilities
    "25800": "BS-OTHERCURRENTLIAB",   # Current Liability - Leases
    "25650": "BS-OTHERCURRENTLIAB",   # Unitholder Entitlements
    "25410": "BS-OTHERCURRENTLIAB",   # Rounding
    "25310": "BS-OTHERCURRENTLIAB",   # Credit cards
    "25311": "BS-OTHERCURRENTLIAB",   # Credit cards
    "25312": "BS-OTHERCURRENTLIAB",   # Credit cards
    "25430": "BS-OTHERCURRENTLIAB",   # Other current liabilities
    "25700": "BS-OTHERCURRENTLIAB",   # Hire Purchase Instalments
    "25200": "BS-OTHERCURRENTLIAB",   # Child support payable
    "22800": "BS-EMPLOYPAYABLES",     # Other Employee Liabilities
    "22700": "BS-EMPLOYPAYABLES",     # Parental leave payable
    "22300": "BS-OTHERCURRENTLIAB",   # FBT Payable
    "OOB2":  "BS-OTHERCURRENTLIAB",   # ABN Withholding
    # Receivables / cash
    "24100": "BS-DEBTORS",     # Provision for Doubtful Debts
    "11901": "BS-CASH",        # Cash at hand
    "12100": "BS-DEBTORS",     # External Receivables
    # Equity
    "32000": "BS-RETAINEDEARNINGS",   # Retained earnings
    "32300": "BS-RETAINEDEARNINGS",   # Profit distributed to Unitholders
    # IS — payroll
    "61150": "OPEX-WAGES",     # Indirect Bonuses
    "61400": "OPEX-WAGES",     # Indirect FBT
    "61600": "OPEX-WAGES",     # Indirect Training
    "61110": "OPEX-LEAVE",     # Parental leave expense
    # IS — general / travel
    "64440": "OPEX-GENERAL",   # Travel - Motor vehicle
    "64250": "OPEX-GENERAL",   # Employee Amenities
    "64430": "OPEX-GENERAL",   # Travel - F&B
    "68200": "OPEX-GENERAL",   # Clearing - Assets to on cost
    "67230": "OPEX-UTILITIES", # Water
    # IS — gains / losses
    "74000": "OPEX-GAINLOSS",  # Loss on Sale of an Asset
    "47000": "OPEX-GAINLOSS",  # Gain on Acquisition
    "49000": "REV-OTHER",      # Dividend received
}


async def run():
    async with async_session_factory() as db:
        # Load accounts
        result = await db.execute(select(Account))
        acct_by_code = {a.code: a for a in result.scalars().all()}

        # Load NetSuite entities
        result = await db.execute(
            select(Entity)
            .where(Entity.is_active.is_(True), Entity.source_system == "netsuite")
            .order_by(Entity.code)
        )
        ns_entities = list(result.scalars().all())
        print(f"Entities: {[e.code for e in ns_entities]}")

        added = 0
        skipped = 0

        for ent in ns_entities:
            effective = ent.acquisition_date or DEFAULT_EFFECTIVE
            for src_code, tgt_code in GLOBAL_MAPPINGS.items():
                tgt = acct_by_code.get(tgt_code)
                if tgt is None:
                    print(f"  WARNING: {tgt_code} not found, skipping {src_code}")
                    continue

                result = await db.execute(
                    select(AccountMapping).where(
                        AccountMapping.entity_id == ent.id,
                        AccountMapping.source_account_code == src_code,
                    )
                )
                if result.scalar_one_or_none():
                    skipped += 1
                    continue

                db.add(AccountMapping(
                    entity_id=ent.id,
                    source_account_code=src_code,
                    target_account_id=tgt.id,
                    multiplier=1.0,
                    effective_from=effective,
                ))
                added += 1

        print(f"Mappings: {added} added, {skipped} already existed")
        await db.commit()

    # Re-consolidate
    print("\nRe-consolidating FY2024 M01-M12...")
    results = []
    for fy_month in range(1, 13):
        print(f"  M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(2024, fy_month)
            async with async_session_factory() as db:
                crun = await db.get(ConsolidationRun, run_id)
                balanced = crun.bs_balanced if crun else None
                variance = crun.bs_variance if crun else None
                results.append((fy_month, balanced, variance))
                unmapped_msg = ""
                print(f"balanced={balanced}, variance={variance}")
        except Exception as exc:
            results.append((fy_month, None, None))
            print(f"FAILED: {exc}")

    # Summary
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
