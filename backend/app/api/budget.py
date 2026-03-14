"""Budget model API — trigger calculation, check status, read outputs."""

from __future__ import annotations

import uuid
from collections import defaultdict

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_finance
from app.db.models.account import Account, AccountType, Statement
from app.db.models.budget import BudgetVersion, ModelOutput
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.user import User
from app.schemas.budget import (
    CalculationStatusResponse,
    CalculationTriggerResponse,
    ModelOutputResponse,
    ModelOutputRow,
)

router = APIRouter(prefix="/budgets", tags=["budgets"])

MONTH_ABBR = [
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
]


def _period_label(period: Period) -> str:
    if period.period_start:
        return period.period_start.strftime("%b-%y")
    cal_year = period.fy_year - 1 if period.fy_month <= 6 else period.fy_year
    return f"{MONTH_ABBR[period.fy_month - 1]}-{cal_year % 100:02d}"


# ── Section header config ────────────────────────────────────────────────────

IS_SECTIONS: dict[str, list[AccountType]] = {
    "Revenue": [AccountType.income, AccountType.cogs],
    "Operating Expenses": [AccountType.opex],
    "Depreciation & Amortisation": [AccountType.depreciation],
    "Interest": [AccountType.interest],
    "Tax": [AccountType.tax],
}

BS_SECTIONS: dict[str, list[AccountType]] = {
    "Assets": [AccountType.asset],
    "Liabilities": [AccountType.liability],
    "Equity": [AccountType.equity],
}

CF_SECTIONS: dict[str, list[str]] = {
    "Operating Activities": ["CF-OPERATING"],
    "Investing Activities": ["CF-INVESTING"],
    "Financing Activities": ["CF-FINANCING"],
    "Net Cash Flow": ["CF-NET"],
}


# ── POST /budgets/{id}/calculate ─────────────────────────────────────────────


@router.post(
    "/{budget_id}/calculate",
    response_model=CalculationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_calculation(
    budget_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    from app.worker import run_model_task

    task = run_model_task.delay(str(budget_id))
    return CalculationTriggerResponse(task_id=task.id, status="queued")


# ── GET /budgets/{id}/status ─────────────────────────────────────────────────


@router.get("/{budget_id}/status", response_model=CalculationStatusResponse)
async def get_calculation_status(
    budget_id: uuid.UUID,
    _user: User = Depends(require_finance),
):
    from app.worker import celery_app

    # Find the most recent task for this budget version.
    # In a production system you'd track task_id on the version row;
    # for now inspect via Celery backend.
    task_key = f"model-{budget_id}"
    result = AsyncResult(task_key, app=celery_app)

    if result.state == "PENDING":
        return CalculationStatusResponse(
            task_id=task_key, status="no_task_found"
        )

    return CalculationStatusResponse(
        task_id=task_key,
        status=result.state.lower(),
        result=result.result if result.successful() else None,
    )


# ── GET /budgets/{id}/output/is ──────────────────────────────────────────────


@router.get("/{budget_id}/output/is", response_model=ModelOutputResponse)
async def get_budget_is(
    budget_id: uuid.UUID,
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    return await _get_model_output(db, budget_id, Statement.is_, fy_month)


@router.get("/{budget_id}/output/bs", response_model=ModelOutputResponse)
async def get_budget_bs(
    budget_id: uuid.UUID,
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    return await _get_model_output(db, budget_id, Statement.bs, fy_month)


@router.get("/{budget_id}/output/cf", response_model=ModelOutputResponse)
async def get_budget_cf(
    budget_id: uuid.UUID,
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    return await _get_model_output(db, budget_id, Statement.cf, fy_month)


# ── Shared output renderer ──────────────────────────────────────────────────


async def _get_model_output(
    db: AsyncSession,
    budget_id: uuid.UUID,
    statement: Statement,
    fy_month: int | None,
) -> ModelOutputResponse:
    version = await db.get(BudgetVersion, budget_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    fy_year = version.fy_year

    # Resolve periods
    if fy_month is not None:
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month <= fy_month)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        target = next((p for p in all_periods if p.fy_month == fy_month), None)
        if target is None:
            raise HTTPException(status_code=404, detail="Period not found")
        period_ids = [p.id for p in all_periods]
        target_label = _period_label(target)
        column_labels = [target_label, "YTD"]
        period_id_to_label = {p.id: _period_label(p) for p in all_periods}
    else:
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        if not all_periods:
            raise HTTPException(status_code=404, detail="No periods for this FY")
        period_ids = [p.id for p in all_periods]
        column_labels = [_period_label(p) for p in all_periods]
        period_id_to_label = {p.id: _period_label(p) for p in all_periods}

    # Load accounts for the statement (or CF pseudo-accounts)
    is_cf = statement == Statement.cf
    if is_cf:
        cf_codes = ["CF-OPERATING", "CF-INVESTING", "CF-FINANCING", "CF-NET"]
        result = await db.execute(
            select(Account).where(Account.code.in_(cf_codes))
        )
        accounts = list(result.scalars().all())
        if not accounts:
            accounts = _build_cf_pseudo_accounts(cf_codes)
    else:
        result = await db.execute(
            select(Account)
            .where(Account.statement == statement)
            .order_by(Account.sort_order)
        )
        accounts = list(result.scalars().all())

    account_ids = [a.id for a in accounts]

    # Load model outputs
    result = await db.execute(
        select(ModelOutput).where(
            ModelOutput.version_id == budget_id,
            ModelOutput.period_id.in_(period_ids),
            ModelOutput.account_id.in_(account_ids),
        )
    )
    model_outputs = result.scalars().all()

    # Load entities
    result = await db.execute(select(Entity))
    entities_map = {e.id: e for e in result.scalars().all()}

    # Index outputs
    group_totals: dict[uuid.UUID, dict[str, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    entity_amounts: dict[uuid.UUID, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )

    for mo in model_outputs:
        label = period_id_to_label.get(mo.period_id)
        if label is None:
            continue
        if mo.entity_id is None:
            group_totals[mo.account_id][label] += float(mo.amount)
        else:
            ent = entities_map.get(mo.entity_id)
            ecode = ent.code if ent else "?"
            entity_amounts[mo.account_id][ecode][label] += float(mo.amount)

    # Build rows with section headers
    rows: list[ModelOutputRow] = []

    if is_cf:
        for section, codes in CF_SECTIONS.items():
            rows.append(ModelOutputRow(
                account_code="",
                label=section,
                is_section_header=True,
            ))
            for acct in accounts:
                if acct.code not in codes:
                    continue
                vals = _build_values(
                    acct, group_totals, column_labels, fy_month, period_id_to_label
                )
                eb = _build_entity_breakdown(
                    acct, entity_amounts, column_labels, fy_month, period_id_to_label
                )
                rows.append(ModelOutputRow(
                    account_code=acct.code,
                    label=acct.name,
                    is_subtotal=getattr(acct, "is_subtotal", False),
                    indent_level=0 if getattr(acct, "is_subtotal", False) else 1,
                    values=vals,
                    entity_breakdown=eb,
                ))
    else:
        sections = BS_SECTIONS if statement == Statement.bs else IS_SECTIONS
        type_to_section: dict[AccountType, str] = {}
        for sec, types in sections.items():
            for t in types:
                type_to_section[t] = sec

        seen_sections: set[str] = set()
        for acct in accounts:
            sec = type_to_section.get(acct.account_type)
            if sec and sec not in seen_sections:
                seen_sections.add(sec)
                rows.append(ModelOutputRow(
                    account_code="",
                    label=sec,
                    is_section_header=True,
                ))

            vals = _build_values(
                acct, group_totals, column_labels, fy_month, period_id_to_label
            )
            eb = _build_entity_breakdown(
                acct, entity_amounts, column_labels, fy_month, period_id_to_label
            )
            rows.append(ModelOutputRow(
                account_code=acct.code,
                label=acct.name,
                is_subtotal=acct.is_subtotal,
                indent_level=0 if acct.is_subtotal else 1,
                values=vals,
                entity_breakdown=eb,
            ))

    return ModelOutputResponse(
        version_id=budget_id,
        fy_year=fy_year,
        statement=statement.value,
        periods=column_labels,
        rows=rows,
    )


def _build_values(
    acct: Account,
    group_totals: dict,
    column_labels: list[str],
    fy_month: int | None,
    period_id_to_label: dict,
) -> dict[str, float]:
    month_totals = group_totals.get(acct.id, {})
    if fy_month is not None:
        target_label = column_labels[0]
        month_val = month_totals.get(target_label, 0.0)
        ytd_sum = sum(month_totals.values())
        return {target_label: month_val, "YTD": ytd_sum}
    return {lbl: month_totals.get(lbl, 0.0) for lbl in column_labels}


def _build_entity_breakdown(
    acct: Account,
    entity_amounts: dict,
    column_labels: list[str],
    fy_month: int | None,
    period_id_to_label: dict,
) -> dict[str, dict[str, float]]:
    eb: dict[str, dict[str, float]] = {}
    for ecode, period_map in entity_amounts.get(acct.id, {}).items():
        if fy_month is not None:
            target_label = column_labels[0]
            eb[ecode] = {
                target_label: period_map.get(target_label, 0.0),
                "YTD": sum(period_map.values()),
            }
        else:
            eb[ecode] = {lbl: period_map.get(lbl, 0.0) for lbl in column_labels}
    return eb


def _build_cf_pseudo_accounts(codes: list[str]) -> list:
    """If CF accounts don't exist in the DB yet, create lightweight objects."""
    from types import SimpleNamespace

    labels = {
        "CF-OPERATING": "Operating Cash Flow",
        "CF-INVESTING": "Investing Cash Flow",
        "CF-FINANCING": "Financing Cash Flow",
        "CF-NET": "Net Cash Flow",
    }
    return [
        SimpleNamespace(
            id=uuid.uuid5(uuid.NAMESPACE_DNS, c),
            code=c,
            name=labels.get(c, c),
            is_subtotal=(c == "CF-NET"),
            account_type=None,
        )
        for c in codes
    ]
