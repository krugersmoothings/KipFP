"""Map unmapped accounts found in FY2025-FY2026 data, then re-consolidate.

Run from the backend container:
    python -m scripts.map_fy2025_accounts
"""

import asyncio
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, func
from app.db.base import async_session_factory
from app.db.models.account import Account, AccountMapping
from app.db.models.consolidation import ConsolidatedActual, ConsolidationRun
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.services.consolidation_engine import consolidate_period

EFFECTIVE = date(2024, 7, 1)

# source_account_code -> (target_coa_code, multiplier)
MAPPINGS: dict[str, tuple[str, float]] = {
    # BS — clearing / cash
    "11602": ("BS-CASH", 1.0),
    # BS — loan receivables (KPT intercompany loans)
    "11527": ("BS-OTHERCURRENT", 1.0),
    "11528": ("BS-OTHERCURRENT", 1.0),
    "11529": ("BS-OTHERCURRENT", 1.0),
    # BS — liabilities
    "25440": ("BS-OTHERCURRENTLIAB", 1.0),
    "25330": ("BS-TAX-PAYABLE", 1.0),
    "25320": ("BS-TAX-PAYABLE", 1.0),
    "25313": ("BS-OTHERCURRENTLIAB", 1.0),
    "22400": ("BS-EMPLOYPAYABLES", 1.0),
    "21100": ("BS-CREDITORS", 1.0),
    "29600": ("BS-DEBT-EQUIP", 1.0),
    "29277": ("BS-DEBT-EQUIP", 1.0),
    "29278": ("BS-DEBT-EQUIP", 1.0),
    "29292": ("BS-DEBT-VEHICLE", 1.0),
    "29293": ("BS-DEBT-VEHICLE", 1.0),
    "29294": ("BS-DEBT-VEHICLE", 1.0),
    # BS — intangibles / equity
    "19154": ("BS-INTANGIBLES", 1.0),
    "17105": ("BS-OTHERCURRENT", 1.0),
    "36000": ("BS-RETAINEDEARNINGS", 1.0),
    "76000": ("BS-RETAINEDEARNINGS", 1.0),
    # IS — revenue
    "45500": ("REV-OTHER", 1.0),
    "73000": ("REV-OTHER", 1.0),
    # IS — COGS
    "52400": ("COGS", 1.0),
    "54100": ("COGS", 1.0),
    # IS — opex
    "61140": ("OPEX-WAGES", 1.0),
    "62000": ("OPEX-CONSULTANTS", 1.0),
    "64180": ("OPEX-MARKETING", 1.0),
    "64260": ("OPEX-GENERAL", 1.0),
    "64410": ("OPEX-GENERAL", 1.0),
    "64450": ("OPEX-GENERAL", 1.0),
    "67210": ("OPEX-UTILITIES", 1.0),
    "67280": ("OPEX-RENT", 1.0),
    # IS — D&A
    "71100": ("DA-AMORT", 1.0),
}

# entity_code -> list of source_account_codes to map
ENTITY_ACCOUNTS: dict[str, list[str]] = {
    "ABH": ["11602", "29600", "45500", "52400", "62000", "64180", "64410", "64450", "67210", "71100"],
    "GOO": ["73000"],
    "HSH": ["67280"],
    "KPT": ["11527", "11528", "11529", "29278"],
    "PFH": ["71100"],
    "SEP": ["22400", "25313", "25320", "29292", "29293", "29294", "54100", "64180", "64260", "64410", "64450"],
    "SH":  ["11602", "17105", "19154", "21100", "25330", "25440", "29277", "36000", "61140", "76000"],
}


async def run():
    async with async_session_factory() as db:
        result = await db.execute(select(Account))
        acct_by_code = {a.code: a for a in result.scalars().all()}

        result = await db.execute(select(Entity).where(Entity.is_active.is_(True)))
        ent_by_code = {e.code: e for e in result.scalars().all()}

        added = 0
        skipped = 0

        for ent_code, src_codes in ENTITY_ACCOUNTS.items():
            entity = ent_by_code.get(ent_code)
            if not entity:
                print(f"  WARNING: entity {ent_code} not found")
                continue

            for src_code in src_codes:
                mapping_def = MAPPINGS.get(src_code)
                if not mapping_def:
                    print(f"  WARNING: no mapping definition for {src_code}")
                    continue

                tgt_code, multiplier = mapping_def
                tgt_acct = acct_by_code.get(tgt_code)
                if not tgt_acct:
                    print(f"  WARNING: target account {tgt_code} not found")
                    continue

                result = await db.execute(
                    select(AccountMapping).where(
                        AccountMapping.entity_id == entity.id,
                        AccountMapping.source_account_code == src_code,
                    )
                )
                if result.scalar_one_or_none():
                    skipped += 1
                    continue

                db.add(AccountMapping(
                    entity_id=entity.id,
                    source_account_code=src_code,
                    source_account_name=None,
                    target_account_id=tgt_acct.id,
                    multiplier=multiplier,
                    effective_from=EFFECTIVE,
                    notes="FY2025-26 new account mapping",
                ))
                added += 1
                print(f"  MAPPED {ent_code}:{src_code} -> {tgt_code}")

        await db.commit()
        print(f"\nMappings added: {added}, skipped (already exist): {skipped}")

    # Re-consolidate all 19 periods
    print("\n" + "=" * 70)
    print("Re-consolidating all 19 periods with new mappings")
    print("=" * 70)

    all_periods = [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 8)]
    for fy_year, fy_month in all_periods:
        print(f"  FY{fy_year} M{fy_month:02d} ... ", end="", flush=True)
        try:
            run_id = await consolidate_period(fy_year, fy_month)
            async with async_session_factory() as db:
                crun = await db.get(ConsolidationRun, run_id)
                status = crun.status.value if crun else "?"
                balanced = crun.bs_balanced if crun else None
                print(f"{status}, BS balanced={balanced}")
        except Exception as exc:
            print(f"FAILED: {exc}")

    # Verify revenue
    print("\n" + "=" * 70)
    print("Revenue verification after re-mapping")
    print("=" * 70)

    async with async_session_factory() as db:
        result = await db.execute(select(Account).where(Account.code == "REV-SALES"))
        rev = result.scalar_one()

        for fy_year, fy_month in all_periods:
            result = await db.execute(
                select(Period).where(Period.fy_year == fy_year, Period.fy_month == fy_month)
            )
            period = result.scalar_one_or_none()
            if not period:
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
            print(f"  FY{fy_year} M{fy_month:02d}  {amt:>14,.2f}  {flag:>10}")

    print("\nDONE")


if __name__ == "__main__":
    asyncio.run(run())
