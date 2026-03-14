"""Budget model engine — 3-statement model (IS, BS, CF).

Takes a budget_version_id and calculates the full financial model for
all 12 periods in the FY. Designed to be invoked as a Celery task after
any assumption change.

Calculation order (strict — each step depends on previous):
  1. Revenue
  2. COGS
  3. Opex
  4. EBITDA (derived)
  5. Working capital (via wc_engine)
  6. Debt waterfall (via debt_engine)
  7. D&A
  8. EBIT → NPBT → Tax → NPAT
  9. Cash flow (indirect method)
 10. Balance sheet assembly + validation
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import async_session_factory
from app.db.models.account import Account
from app.db.models.budget import BudgetVersion, ModelAssumption, ModelOutput, VersionStatus
from app.db.models.consolidation import ConsolidatedActual
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.services.debt_engine import calculate_debt_waterfall
from app.services.wc_engine import calculate_wc_schedule

logger = logging.getLogger(__name__)

D = Decimal
ZERO = D("0")
BS_TOLERANCE = D("1.00")


# ── Helper: resolve assumption value ──────────────────────────────────────────


def _get_assumption(
    assumptions: dict[tuple[str, uuid.UUID | None], dict],
    key: str,
    entity_id: uuid.UUID | None = None,
    field: str = "value",
    default: Decimal = ZERO,
) -> Decimal:
    """Look up an assumption, falling back from entity-scoped to global."""
    row = assumptions.get((key, entity_id))
    if row is None and entity_id is not None:
        row = assumptions.get((key, None))
    if row is None:
        return default
    val = row.get(field, row.get("value"))
    if val is None:
        return default
    return D(str(val))


# ── Main entry point ──────────────────────────────────────────────────────────


async def run_model(version_id: uuid.UUID) -> dict:
    """Execute the full model for a budget version. Returns summary stats."""
    async with async_session_factory() as db:
        return await _run_model_inner(db, version_id)


async def _run_model_inner(db: AsyncSession, version_id: uuid.UUID) -> dict:
    # ── Load version ──────────────────────────────────────────────────────
    version = await db.get(BudgetVersion, version_id)
    if version is None:
        raise ValueError(f"Budget version {version_id} not found")
    if version.status == VersionStatus.locked:
        raise ValueError(f"Budget version {version_id} is locked")

    fy_year = version.fy_year

    # ── Load periods (12 months) ──────────────────────────────────────────
    result = await db.execute(
        select(Period)
        .where(Period.fy_year == fy_year)
        .order_by(Period.fy_month)
    )
    periods = list(result.scalars().all())
    if not periods:
        raise ValueError(f"No periods found for FY{fy_year}")

    # ── Load entities ─────────────────────────────────────────────────────
    result = await db.execute(
        select(Entity).where(Entity.is_active.is_(True))
    )
    entities = list(result.scalars().all())
    entity_ids = {e.id for e in entities}

    # ── Load accounts (by code) ───────────────────────────────────────────
    result = await db.execute(select(Account).order_by(Account.sort_order))
    all_accounts = list(result.scalars().all())
    acct_by_code: dict[str, Account] = {a.code: a for a in all_accounts}

    # ── Load assumptions ──────────────────────────────────────────────────
    result = await db.execute(
        select(ModelAssumption).where(
            ModelAssumption.budget_version_id == version_id
        )
    )
    raw_assumptions = result.scalars().all()

    # Key: (assumption_key, entity_id) → assumption_value (JSONB dict)
    assumptions: dict[tuple[str, uuid.UUID | None], dict] = {}
    for a in raw_assumptions:
        assumptions[(a.assumption_key, a.entity_id)] = a.assumption_value

    # ── Load prior-year actuals for growth-based calcs ────────────────────
    prior_fy = fy_year - 1
    result = await db.execute(
        select(Period).where(Period.fy_year == prior_fy).order_by(Period.fy_month)
    )
    prior_periods = list(result.scalars().all())
    prior_period_ids = [p.id for p in prior_periods]

    prior_actuals: dict[tuple[str, int], Decimal] = {}
    if prior_period_ids:
        result = await db.execute(
            select(ConsolidatedActual).where(
                ConsolidatedActual.period_id.in_(prior_period_ids),
                ConsolidatedActual.is_group_total.is_(True),
            )
        )
        for act in result.scalars().all():
            acct = acct_by_code.get(
                next(
                    (a.code for a in all_accounts if a.id == act.account_id),
                    "",
                )
            )
            if acct:
                pp = next(
                    (p for p in prior_periods if p.id == act.period_id), None
                )
                if pp:
                    prior_actuals[(acct.code, pp.fy_month)] = D(str(act.amount))

    # ── Storage: outputs[(account_code, period_id)] = Decimal ─────────────
    outputs: dict[tuple[str, uuid.UUID], Decimal] = {}
    entity_outputs: dict[tuple[str, uuid.UUID, uuid.UUID], Decimal] = {}

    # ── STEP 1: REVENUE ───────────────────────────────────────────────────
    for entity in entities:
        for idx, period in enumerate(periods):
            key_growth = f"revenue.{entity.code}.growth_rate"
            key_manual = f"revenue.{entity.code}.manual"

            manual_val = _get_assumption(
                assumptions, key_manual, entity.id, "value"
            )
            if manual_val != ZERO:
                rev = manual_val
            else:
                growth = _get_assumption(
                    assumptions, key_growth, entity.id, "value"
                )
                if idx == 0:
                    prior_rev = prior_actuals.get(("REV-SALES", period.fy_month), ZERO)
                else:
                    prior_rev = entity_outputs.get(
                        ("REV-SALES", periods[idx - 1].id, entity.id), ZERO
                    )
                rev = prior_rev * (D("1") + growth)

            entity_outputs[("REV-SALES", period.id, entity.id)] = rev

    _aggregate_entity_to_group(entity_outputs, outputs, "REV-SALES", periods, entities)

    # ── STEP 2: COGS ─────────────────────────────────────────────────────
    for entity in entities:
        cogs_pct = _get_assumption(
            assumptions, "cogs.pct_revenue", entity.id, "value"
        )
        for period in periods:
            rev = entity_outputs.get(("REV-SALES", period.id, entity.id), ZERO)
            cogs = rev * cogs_pct
            entity_outputs[("COGS", period.id, entity.id)] = cogs

    _aggregate_entity_to_group(entity_outputs, outputs, "COGS", periods, entities)

    # ── STEP 3: OPEX ─────────────────────────────────────────────────────
    opex_codes = [
        "OPEX-WAGES", "OPEX-SUPER", "OPEX-LEAVE", "OPEX-PAYROLLTAX",
        "OPEX-MARKETING", "OPEX-CONSULTANTS", "OPEX-GENERAL",
        "OPEX-UTILITIES", "OPEX-RandM", "OPEX-RENT", "OPEX-IT",
    ]

    for code in opex_codes:
        for entity in entities:
            driver_key = f"opex.{code}.driver_type"
            driver_type = _get_assumption(
                assumptions, driver_key, entity.id, "value", default=D("-1")
            )
            value_key = f"opex.{code}.value"

            for idx, period in enumerate(periods):
                driver_str = str(driver_type) if driver_type != D("-1") else "fixed"

                if driver_str == "manual":
                    amt = _get_assumption(
                        assumptions,
                        f"opex.{code}.m{period.fy_month}",
                        entity.id,
                        "value",
                    )
                elif driver_str == "pct_revenue":
                    pct = _get_assumption(assumptions, value_key, entity.id, "value")
                    rev = entity_outputs.get(("REV-SALES", period.id, entity.id), ZERO)
                    amt = rev * pct
                elif driver_str == "growth":
                    growth_rate = _get_assumption(
                        assumptions, value_key, entity.id, "value"
                    )
                    prior_val = prior_actuals.get((code, period.fy_month), ZERO)
                    amt = prior_val * (D("1") + growth_rate)
                else:
                    amt = _get_assumption(assumptions, value_key, entity.id, "value")

                entity_outputs[(code, period.id, entity.id)] = amt

        _aggregate_entity_to_group(entity_outputs, outputs, code, periods, entities)

    # OPEX-TOTAL
    for period in periods:
        total = sum(outputs.get((c, period.id), ZERO) for c in opex_codes)
        outputs[("OPEX-TOTAL", period.id)] = total

    # ── STEP 4: EBITDA ───────────────────────────────────────────────────
    for period in periods:
        rev = outputs.get(("REV-SALES", period.id), ZERO)
        other_rev = outputs.get(("REV-OTHER", period.id), ZERO)
        cogs = outputs.get(("COGS", period.id), ZERO)
        gm = rev + other_rev - cogs
        outputs[("GM", period.id)] = gm
        opex_total = outputs.get(("OPEX-TOTAL", period.id), ZERO)
        ebitda = gm - opex_total
        outputs[("EBITDA", period.id)] = ebitda

    # ── STEP 5: WORKING CAPITAL ──────────────────────────────────────────
    rev_by_ep: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = {}
    cogs_by_ep: dict[tuple[uuid.UUID, uuid.UUID], Decimal] = {}
    for entity in entities:
        for period in periods:
            rev_by_ep[(entity.id, period.id)] = entity_outputs.get(
                ("REV-SALES", period.id, entity.id), ZERO
            )
            cogs_by_ep[(entity.id, period.id)] = entity_outputs.get(
                ("COGS", period.id, entity.id), ZERO
            )

    wc_result = await calculate_wc_schedule(
        db, version_id, periods, rev_by_ep, cogs_by_ep
    )

    wc_movements = wc_result.movements_by_period()
    wc_closing = wc_result.closing_by_account_period()

    # Map WC closing balances to BS accounts
    for (acct_id, period_id), closing in wc_closing.items():
        acct = next((a for a in all_accounts if a.id == acct_id), None)
        if acct:
            outputs[(acct.code, period_id)] = closing

    # ── STEP 6: DEBT WATERFALL ───────────────────────────────────────────
    debt_result = await calculate_debt_waterfall(
        db, version_id, periods, entity_ids
    )

    interest_by_period = debt_result.total_interest_by_period()
    repayment_by_period = debt_result.total_repayment_by_period()
    drawdown_by_period = debt_result.total_drawdown_by_period()
    debt_closing_by_period = debt_result.total_closing_by_period()

    for period in periods:
        outputs[("INT-EXPENSE", period.id)] = interest_by_period.get(period.id, ZERO)

    # ── STEP 7: D&A ─────────────────────────────────────────────────────
    for period in periods:
        depn = _get_assumption(assumptions, "da.depreciation.monthly", field="value")
        amort = _get_assumption(assumptions, "da.amortisation.monthly", field="value")
        outputs[("DA-DEPN", period.id)] = depn
        outputs[("DA-AMORT", period.id)] = amort
        outputs[("DA-TOTAL", period.id)] = depn + amort

    # ── STEP 8: EBIT → NPBT → Tax → NPAT ────────────────────────────────
    tax_rate = _get_assumption(assumptions, "tax.effective_rate", field="value")

    for period in periods:
        ebitda = outputs.get(("EBITDA", period.id), ZERO)
        da_total = outputs.get(("DA-TOTAL", period.id), ZERO)
        ebit = ebitda - da_total
        outputs[("EBIT", period.id)] = ebit

        int_income = _get_assumption(
            assumptions, "interest.income.monthly", field="value"
        )
        outputs[("INT-INCOME", period.id)] = int_income
        int_expense = outputs.get(("INT-EXPENSE", period.id), ZERO)
        int_net = int_expense - int_income
        outputs[("INT-NET", period.id)] = int_net

        npbt = ebit - int_net
        outputs[("NPBT", period.id)] = npbt

        tax = npbt * tax_rate if npbt > ZERO else ZERO
        outputs[("TAX", period.id)] = tax

        npat = npbt - tax
        outputs[("NPAT", period.id)] = npat

    # ── STEP 9: CASH FLOW (indirect method) ──────────────────────────────
    capex_monthly = _get_assumption(assumptions, "capex.monthly", field="value")

    for idx, period in enumerate(periods):
        npat = outputs.get(("NPAT", period.id), ZERO)
        da_total = outputs.get(("DA-TOTAL", period.id), ZERO)
        wc_movement = wc_movements.get(period.id, ZERO)

        operating_cf = npat + da_total - wc_movement
        outputs[("CF-OPERATING", period.id)] = operating_cf

        investing_cf = -capex_monthly
        outputs[("CF-INVESTING", period.id)] = investing_cf

        repay = repayment_by_period.get(period.id, ZERO)
        draw = drawdown_by_period.get(period.id, ZERO)
        financing_cf = draw - repay
        outputs[("CF-FINANCING", period.id)] = financing_cf

        net_cf = operating_cf + investing_cf + financing_cf
        outputs[("CF-NET", period.id)] = net_cf

        if idx == 0:
            opening_cash = prior_actuals.get(("BS-CASH", 12), ZERO)
        else:
            opening_cash = outputs.get(("BS-CASH", periods[idx - 1].id), ZERO)

        closing_cash = opening_cash + net_cf
        outputs[("BS-CASH", period.id)] = closing_cash

    # ── STEP 10: BALANCE SHEET ───────────────────────────────────────────
    for idx, period in enumerate(periods):
        if idx == 0:
            prior_ppe = prior_actuals.get(("BS-PPE", 12), ZERO)
            prior_re = prior_actuals.get(("BS-RETAINEDEARNINGS", 12), ZERO)
        else:
            prior_ppe = outputs.get(("BS-PPE", periods[idx - 1].id), ZERO)
            prior_re = outputs.get(
                ("BS-RETAINEDEARNINGS", periods[idx - 1].id), ZERO
            )

        depn = outputs.get(("DA-DEPN", period.id), ZERO)
        ppe = prior_ppe + capex_monthly - depn
        outputs[("BS-PPE", period.id)] = ppe

        npat = outputs.get(("NPAT", period.id), ZERO)
        outputs[("BS-RETAINEDEARNINGS", period.id)] = prior_re + npat

        outputs[("BS-TOTALDEBT", period.id)] = debt_closing_by_period.get(
            period.id, ZERO
        )

    # Calculate subtotals using the same formulas as the COA
    _calculate_subtotals(outputs, all_accounts, periods)

    # BS validation
    warnings: list[str] = []
    for period in periods:
        total_assets = outputs.get(("BS-TOTALASSETS", period.id), ZERO)
        total_liab = outputs.get(("BS-TOTALLIAB", period.id), ZERO)
        total_equity = outputs.get(("BS-TOTALEQUITY", period.id), ZERO)
        variance = total_assets - (total_liab + total_equity)
        if abs(variance) > BS_TOLERANCE:
            msg = (
                f"BS imbalance M{period.fy_month:02d}: "
                f"Assets={total_assets}, L+E={total_liab + total_equity}, "
                f"variance={variance}"
            )
            warnings.append(msg)
            logger.warning(msg)

    # ── PERSIST: upsert to model_outputs ─────────────────────────────────
    await _write_outputs(db, version_id, outputs, entity_outputs, acct_by_code)
    await db.commit()

    rows_written = len(outputs) + len(entity_outputs)
    logger.info(
        "Model engine complete: version=%s FY%d, %d output rows, %d warnings",
        version_id, fy_year, rows_written, len(warnings),
    )
    return {
        "version_id": str(version_id),
        "fy_year": fy_year,
        "rows_written": rows_written,
        "warnings": warnings,
    }


# ── Internal helpers ──────────────────────────────────────────────────────────


def _aggregate_entity_to_group(
    entity_outputs: dict[tuple[str, uuid.UUID, uuid.UUID], Decimal],
    outputs: dict[tuple[str, uuid.UUID], Decimal],
    code: str,
    periods: list[Period],
    entities: list[Entity],
) -> None:
    """Sum entity-level amounts to group-level for a given account code."""
    for period in periods:
        total = sum(
            entity_outputs.get((code, period.id, e.id), ZERO) for e in entities
        )
        outputs[(code, period.id)] = total


def _calculate_subtotals(
    outputs: dict[tuple[str, uuid.UUID], Decimal],
    all_accounts: list[Account],
    periods: list[Period],
) -> None:
    """Recompute subtotal accounts using their formulas, skipping any
    that are already set (like EBITDA, NPAT which are computed inline)."""
    subtotals = [a for a in all_accounts if a.is_subtotal and a.subtotal_formula]

    for acct in subtotals:
        for period in periods:
            if (acct.code, period.id) in outputs:
                continue

            formula = acct.subtotal_formula
            total = ZERO
            for c in formula.get("add", []):
                total += outputs.get((c, period.id), ZERO)
            for c in formula.get("subtract", []):
                total -= outputs.get((c, period.id), ZERO)
            outputs[(acct.code, period.id)] = total


async def _write_outputs(
    db: AsyncSession,
    version_id: uuid.UUID,
    outputs: dict[tuple[str, uuid.UUID], Decimal],
    entity_outputs: dict[tuple[str, uuid.UUID, uuid.UUID], Decimal],
    acct_by_code: dict[str, Account],
) -> None:
    """Upsert all computed values into model_outputs."""
    now = datetime.now(timezone.utc)

    await db.execute(
        delete(ModelOutput).where(ModelOutput.version_id == version_id)
    )

    batch: list[dict] = []

    for (code, period_id), amount in outputs.items():
        acct = acct_by_code.get(code)
        if acct is None:
            continue
        batch.append({
            "version_id": version_id,
            "period_id": period_id,
            "account_id": acct.id,
            "entity_id": None,
            "amount": float(amount),
            "calculated_at": now,
        })

    for (code, period_id, entity_id), amount in entity_outputs.items():
        acct = acct_by_code.get(code)
        if acct is None:
            continue
        batch.append({
            "version_id": version_id,
            "period_id": period_id,
            "account_id": acct.id,
            "entity_id": entity_id,
            "amount": float(amount),
            "calculated_at": now,
        })

    if batch:
        stmt = pg_insert(ModelOutput).values(batch)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_model_outputs_version_period_account_entity",
            set_={
                "amount": stmt.excluded.amount,
                "calculated_at": stmt.excluded.calculated_at,
            },
        )
        await db.execute(stmt)

    logger.info("Wrote %d model_output rows for version %s", len(batch), version_id)
