"""Seed canonical KipFP Chart of Accounts + account mappings.

Run from the backend container:
    python -m scripts.seed_coa
"""

import asyncio
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.models.account import (
    Account,
    AccountMapping,
    AccountType,
    NormalBalance,
    Statement,
)
from app.db.models.entity import Entity

# ── IS accounts ──────────────────────────────────────────────────────────────

IS_ACCOUNTS: list[dict] = [
    {"code": "REV-SALES",        "name": "Sales Revenue",               "type": AccountType.income,       "nb": NormalBalance.credit},
    {"code": "REV-OTHER",        "name": "Other Revenue",               "type": AccountType.income,       "nb": NormalBalance.credit},
    {"code": "COGS",             "name": "Cost of Goods Sold",          "type": AccountType.cogs,         "nb": NormalBalance.debit},
    {"code": "GM",               "name": "Gross Margin",                "type": AccountType.income,       "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["REV-SALES", "REV-OTHER"], "subtract": ["COGS"]}},
    {"code": "OPEX-WAGES",       "name": "Wages & Salaries",            "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-SUPER",       "name": "Superannuation",              "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-LEAVE",       "name": "Leave Provisions",            "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-PAYROLLTAX",  "name": "Payroll Tax",                 "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-MARKETING",   "name": "Marketing & Advertising",     "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-CONSULTANTS", "name": "Consultants & Professional",  "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-GENERAL",     "name": "General & Admin Expenses",    "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-UTILITIES",   "name": "Utilities",                   "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-RandM",       "name": "Repairs & Maintenance",       "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-RENT",        "name": "Rent & Occupancy",            "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-IT",          "name": "IT & Software",               "type": AccountType.opex,         "nb": NormalBalance.debit},
    {"code": "OPEX-TOTAL",       "name": "Total Operating Expenses",    "type": AccountType.opex,         "nb": NormalBalance.debit,   "subtotal": True, "formula": {"add": ["OPEX-WAGES","OPEX-SUPER","OPEX-LEAVE","OPEX-PAYROLLTAX","OPEX-MARKETING","OPEX-CONSULTANTS","OPEX-GENERAL","OPEX-UTILITIES","OPEX-RandM","OPEX-RENT","OPEX-IT"]}},
    {"code": "EBITDA",           "name": "EBITDA",                      "type": AccountType.income,       "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["GM"], "subtract": ["OPEX-TOTAL"]}},
    {"code": "DA-DEPN",          "name": "Depreciation",                "type": AccountType.depreciation, "nb": NormalBalance.debit},
    {"code": "DA-AMORT",         "name": "Amortisation",                "type": AccountType.depreciation, "nb": NormalBalance.debit},
    {"code": "DA-TOTAL",         "name": "Total D&A",                   "type": AccountType.depreciation, "nb": NormalBalance.debit,   "subtotal": True, "formula": {"add": ["DA-DEPN","DA-AMORT"]}},
    {"code": "EBIT",             "name": "EBIT",                        "type": AccountType.income,       "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["EBITDA"], "subtract": ["DA-TOTAL"]}},
    {"code": "INT-INCOME",       "name": "Interest Income",             "type": AccountType.interest,     "nb": NormalBalance.credit},
    {"code": "INT-EXPENSE",      "name": "Interest Expense",            "type": AccountType.interest,     "nb": NormalBalance.debit},
    {"code": "INT-NET",          "name": "Net Interest",                "type": AccountType.interest,     "nb": NormalBalance.debit,   "subtotal": True, "formula": {"add": ["INT-EXPENSE"], "subtract": ["INT-INCOME"]}},
    {"code": "NPBT",             "name": "Net Profit Before Tax",       "type": AccountType.income,       "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["EBIT"], "subtract": ["INT-NET"]}},
    {"code": "TAX",              "name": "Income Tax Expense",          "type": AccountType.tax,          "nb": NormalBalance.debit},
    {"code": "NPAT",             "name": "Net Profit After Tax",        "type": AccountType.income,       "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["NPBT"], "subtract": ["TAX"]}},
]

# ── BS accounts ──────────────────────────────────────────────────────────────

BS_ACCOUNTS: list[dict] = [
    {"code": "BS-CASH",              "name": "Cash & Cash Equivalents",      "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-DEBTORS",           "name": "Trade Debtors",                "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-INVENTORY",         "name": "Inventory",                    "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-PREPAYMENTS",       "name": "Prepayments",                  "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-OTHERCURRENT",      "name": "Other Current Assets",         "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-TOTALCURRENT",      "name": "Total Current Assets",         "type": AccountType.asset,     "nb": NormalBalance.debit,   "subtotal": True, "formula": {"add": ["BS-CASH","BS-DEBTORS","BS-INVENTORY","BS-PREPAYMENTS","BS-OTHERCURRENT"]}},
    {"code": "BS-PPE",               "name": "Property, Plant & Equipment",  "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-GOODWILL",          "name": "Goodwill",                     "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-ROU",               "name": "Right-of-Use Assets",          "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-INTANGIBLES",       "name": "Intangible Assets",            "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-DEFTAX",            "name": "Deferred Tax Assets",          "type": AccountType.asset,     "nb": NormalBalance.debit},
    {"code": "BS-TOTALNONCURRENT",   "name": "Total Non-Current Assets",     "type": AccountType.asset,     "nb": NormalBalance.debit,   "subtotal": True, "formula": {"add": ["BS-PPE","BS-GOODWILL","BS-ROU","BS-INTANGIBLES","BS-DEFTAX"]}},
    {"code": "BS-TOTALASSETS",       "name": "Total Assets",                 "type": AccountType.asset,     "nb": NormalBalance.debit,   "subtotal": True, "formula": {"add": ["BS-TOTALCURRENT","BS-TOTALNONCURRENT"]}},
    {"code": "BS-CREDITORS",         "name": "Trade Creditors",              "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-EMPLOYPAYABLES",    "name": "Employee Payables",            "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-GST",               "name": "GST Payable/Receivable",       "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-TAX-PAYABLE",       "name": "Tax Payable",                  "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-UNEARNEDREV",       "name": "Unearned Revenue",             "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-OTHERCURRENTLIAB",  "name": "Other Current Liabilities",    "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-TOTALCURRENTLIAB",  "name": "Total Current Liabilities",    "type": AccountType.liability, "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["BS-CREDITORS","BS-EMPLOYPAYABLES","BS-GST","BS-TAX-PAYABLE","BS-UNEARNEDREV","BS-OTHERCURRENTLIAB"]}},
    {"code": "BS-DEBT-11514",        "name": "Debt Facility 11514",          "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-DEBT-11516",        "name": "Debt Facility 11516",          "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-DEBT-11518",        "name": "Debt Facility 11518",          "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-DEBT-11524",        "name": "Debt Facility 11524",          "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-DEBT-11525",        "name": "Debt Facility 11525",          "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-DEBT-EQUIP",        "name": "Equipment Finance",            "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-DEBT-VEHICLE",      "name": "Vehicle Finance",              "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-TOTALDEBT",         "name": "Total Debt",                   "type": AccountType.liability, "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["BS-DEBT-11514","BS-DEBT-11516","BS-DEBT-11518","BS-DEBT-11524","BS-DEBT-11525","BS-DEBT-EQUIP","BS-DEBT-VEHICLE"]}},
    {"code": "BS-PROVISIONS",        "name": "Provisions",                   "type": AccountType.liability, "nb": NormalBalance.credit},
    {"code": "BS-TOTALNONCURRENTLIAB","name": "Total Non-Current Liabilities","type": AccountType.liability,"nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["BS-TOTALDEBT","BS-PROVISIONS"]}},
    {"code": "BS-TOTALLIAB",         "name": "Total Liabilities",            "type": AccountType.liability, "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["BS-TOTALCURRENTLIAB","BS-TOTALNONCURRENTLIAB"]}},
    {"code": "BS-RETAINEDEARNINGS",  "name": "Retained Earnings",            "type": AccountType.equity,    "nb": NormalBalance.credit},
    {"code": "BS-TOTALEQUITY",       "name": "Total Equity",                 "type": AccountType.equity,    "nb": NormalBalance.credit,  "subtotal": True, "formula": {"add": ["BS-RETAINEDEARNINGS"]}},
]

# ── NetSuite account mappings for ALL SH subsidiaries ─────────────────────

# effective_from for most SH entities
SH_DEFAULT_EFFECTIVE = date(2021, 7, 1)

NS_MAPPINGS_SH: list[dict] = [
    # Revenue
    {"src": "41000", "tgt": "REV-SALES"},
    {"src": "42000", "tgt": "REV-OTHER"},
    {"src": "43000", "tgt": "REV-OTHER"},
    {"src": "48000", "tgt": "REV-SALES"},
    # COGS
    {"src": "52100", "tgt": "COGS"},
    {"src": "52300", "tgt": "COGS"},
    {"src": "53100", "tgt": "COGS"},
    # Payroll
    {"src": "61100", "tgt": "OPEX-WAGES"},
    {"src": "61300", "tgt": "OPEX-SUPER"},
    {"src": "61500", "tgt": "OPEX-PAYROLLTAX"},
    {"src": "61850", "tgt": "OPEX-LEAVE"},
    # Consultants
    {"src": "62100", "tgt": "OPEX-CONSULTANTS"},
    {"src": "62200", "tgt": "OPEX-CONSULTANTS"},
    {"src": "62300", "tgt": "OPEX-CONSULTANTS", "notes": "IC: MC management fee"},
    {"src": "62400", "tgt": "OPEX-CONSULTANTS"},
    {"src": "62600", "tgt": "OPEX-CONSULTANTS"},
    # R&M
    {"src": "63100", "tgt": "OPEX-RandM"},
    {"src": "63200", "tgt": "OPEX-RandM"},
    {"src": "63300", "tgt": "OPEX-RandM"},
    {"src": "63400", "tgt": "OPEX-RandM"},
    # General (64000-64900)
    *[{"src": str(c), "tgt": "OPEX-GENERAL"} for c in range(64000, 64901, 100)],
    # Marketing (65000-65600)
    *[{"src": str(c), "tgt": "OPEX-MARKETING"} for c in range(65000, 65601, 100)],
    # IT (66000-66400)
    *[{"src": str(c), "tgt": "OPEX-IT"} for c in range(66000, 66401, 100)],
    # Rent & utilities
    {"src": "67100", "tgt": "OPEX-RENT"},
    {"src": "67200", "tgt": "OPEX-UTILITIES"},
    # D&A
    {"src": "69001", "tgt": "DA-DEPN"},
    {"src": "69002", "tgt": "DA-DEPN"},
    {"src": "69006", "tgt": "DA-AMORT"},
    # Interest
    {"src": "71000", "tgt": "INT-EXPENSE"},
    # BS — Cash (11000-11309)
    *[{"src": str(c), "tgt": "BS-CASH"} for c in range(11000, 11310)],
    # BS — Debt facilities
    {"src": "11514", "tgt": "BS-DEBT-11514"},
    {"src": "11516", "tgt": "BS-DEBT-11516"},
    {"src": "11518", "tgt": "BS-DEBT-11518"},
    {"src": "11524", "tgt": "BS-DEBT-11524"},
    {"src": "11525", "tgt": "BS-DEBT-11525"},
    # BS — Equipment finance (29211-29276)
    *[{"src": str(c), "tgt": "BS-DEBT-EQUIP"} for c in range(29211, 29277)],
    # BS — Vehicle finance (29280-29291)
    *[{"src": str(c), "tgt": "BS-DEBT-VEHICLE"} for c in range(29280, 29292)],
]

# ── Xero account mappings for MC ─────────────────────────────────────────

MC_EFFECTIVE = date(2023, 1, 1)

XERO_MAPPINGS_MC: list[dict] = [
    {"src": "Sales",                  "tgt": "REV-SALES",        "multiplier": -1.0, "notes": "IC elimination: MC mgmt fee"},
    {"src": "Interest Income",        "tgt": "INT-INCOME"},
    {"src": "Other Revenue",          "tgt": "REV-OTHER"},
    {"src": "Bank Fees",              "tgt": "OPEX-GENERAL"},
    {"src": "Consulting & Accounting","tgt": "OPEX-CONSULTANTS"},
    {"src": "General Expenses",       "tgt": "OPEX-GENERAL"},
    {"src": "Interest Expense",       "tgt": "INT-EXPENSE"},
    {"src": "Legal expenses",         "tgt": "OPEX-CONSULTANTS"},
    {"src": "Office Expenses",        "tgt": "OPEX-GENERAL"},
    {"src": "Subscriptions",          "tgt": "OPEX-IT"},
    {"src": "Wages and Salaries",     "tgt": "OPEX-WAGES"},
    {"src": "Superannuation",         "tgt": "OPEX-SUPER"},
    {"src": "Income Tax Expense",     "tgt": "TAX"},
]


async def seed():
    async with async_session_factory() as db:
        db: AsyncSession

        # ── 1. Check if accounts already seeded ──────────────────────────
        existing = await db.execute(select(Account.id).limit(1))
        if existing.scalar_one_or_none() is not None:
            print("Accounts already seeded, skipping")
            return

        # ── 2. Insert IS accounts ────────────────────────────────────────
        acct_map: dict[str, uuid.UUID] = {}
        sort_order = 100

        for a in IS_ACCOUNTS:
            acct_id = uuid.uuid4()
            acct_map[a["code"]] = acct_id
            db.add(Account(
                id=acct_id,
                code=a["code"],
                name=a["name"],
                account_type=a["type"],
                statement=Statement.is_,
                sort_order=sort_order,
                is_subtotal=a.get("subtotal", False),
                subtotal_formula=a.get("formula"),
                normal_balance=a.get("nb"),
            ))
            sort_order += 10

        print(f"Inserted {len(IS_ACCOUNTS)} IS accounts")

        # ── 3. Insert BS accounts ────────────────────────────────────────
        sort_order = 2000
        for a in BS_ACCOUNTS:
            acct_id = uuid.uuid4()
            acct_map[a["code"]] = acct_id
            db.add(Account(
                id=acct_id,
                code=a["code"],
                name=a["name"],
                account_type=a["type"],
                statement=Statement.bs,
                sort_order=sort_order,
                is_subtotal=a.get("subtotal", False),
                subtotal_formula=a.get("formula"),
                normal_balance=a.get("nb"),
            ))
            sort_order += 10

        print(f"Inserted {len(BS_ACCOUNTS)} BS accounts")
        await db.flush()

        # ── 4. NetSuite mappings for all SH entities ─────────────────────
        result = await db.execute(
            select(Entity).where(Entity.source_system == "netsuite")
        )
        ns_entities = result.scalars().all()

        ns_mapping_count = 0
        for entity in ns_entities:
            effective = entity.acquisition_date or SH_DEFAULT_EFFECTIVE
            for m in NS_MAPPINGS_SH:
                target_id = acct_map.get(m["tgt"])
                if target_id is None:
                    print(f"  WARNING: target account {m['tgt']} not found, skipping")
                    continue
                db.add(AccountMapping(
                    entity_id=entity.id,
                    source_account_code=m["src"],
                    target_account_id=target_id,
                    multiplier=m.get("multiplier", 1.0),
                    effective_from=effective,
                    notes=m.get("notes"),
                ))
                ns_mapping_count += 1

        print(f"Inserted {ns_mapping_count} NetSuite mappings across {len(ns_entities)} entities")

        # ── 5. Xero mappings for MC ──────────────────────────────────────
        result = await db.execute(
            select(Entity).where(Entity.code == "MOD")
        )
        mc_entity = result.scalar_one_or_none()

        xero_count = 0
        if mc_entity:
            effective = mc_entity.acquisition_date or MC_EFFECTIVE
            for m in XERO_MAPPINGS_MC:
                target_id = acct_map.get(m["tgt"])
                if target_id is None:
                    print(f"  WARNING: target account {m['tgt']} not found, skipping")
                    continue
                db.add(AccountMapping(
                    entity_id=mc_entity.id,
                    source_account_code=m["src"],
                    target_account_id=target_id,
                    multiplier=m.get("multiplier", 1.0),
                    effective_from=effective,
                    notes=m.get("notes"),
                ))
                xero_count += 1
            print(f"Inserted {xero_count} Xero mappings for MOD (Modulus Capital)")
        else:
            print("WARNING: MOD entity not found — skipping Xero mappings")

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(seed())
