import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, require_finance
from app.db.models.account import Account, AccountType, Statement
from app.db.models.consolidation import ConsolidatedActual
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.user import User
from app.schemas.consolidation import (
    ConsolidationTriggerResponse,
    FinancialRow,
    FinancialStatementResponse,
)

router = APIRouter(tags=["consolidation"])

MONTH_ABBR = [
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
]


def _period_label(period: Period) -> str:
    """Build a human label like 'Jul-23' from a Period object."""
    if period.period_start:
        return period.period_start.strftime("%b-%y")
    # fy_month 1-6 = Jul-Dec of (fy_year - 1), fy_month 7-12 = Jan-Jun of fy_year
    cal_year = period.fy_year - 1 if period.fy_month <= 6 else period.fy_year
    return f"{MONTH_ABBR[period.fy_month - 1]}-{cal_year % 100:02d}"


SECTION_HEADERS: dict[str, list[AccountType]] = {
    "Revenue": [AccountType.income, AccountType.cogs],
    "Operating Expenses": [AccountType.opex],
    "Depreciation & Amortisation": [AccountType.depreciation],
    "Interest": [AccountType.interest],
    "Tax": [AccountType.tax],
}

BS_SECTION_HEADERS: dict[str, list[AccountType]] = {
    "Assets": [AccountType.asset],
    "Liabilities": [AccountType.liability],
    "Equity": [AccountType.equity],
}


def _insert_section_headers(
    accounts: list[Account],
    statement: Statement,
) -> list[tuple[Account | None, str | None]]:
    """Return accounts interleaved with section header markers."""
    headers = BS_SECTION_HEADERS if statement == Statement.bs else SECTION_HEADERS
    type_to_section: dict[AccountType, str] = {}
    for section, types in headers.items():
        for t in types:
            type_to_section[t] = section

    result: list[tuple[Account | None, str | None]] = []
    seen_sections: set[str] = set()

    for acct in accounts:
        section = type_to_section.get(acct.account_type)
        if section and section not in seen_sections:
            seen_sections.add(section)
            result.append((None, section))
        result.append((acct, None))

    return result


@router.post(
    "/consolidate/{fy_year}/{fy_month}",
    response_model=ConsolidationTriggerResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_consolidation(
    fy_year: int,
    fy_month: int,
    _user: User = Depends(require_admin),
):
    """Trigger consolidation for a period via Celery."""
    from app.worker import consolidate_period_task

    task = consolidate_period_task.delay(fy_year, fy_month)
    return ConsolidationTriggerResponse(
        consolidation_run_id=uuid.UUID(int=0),
        status="queued",
    )


@router.get(
    "/consolidated/is",
    response_model=FinancialStatementResponse,
)
async def get_consolidated_is(
    fy_year: int = Query(...),
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Consolidated Income Statement. Omit fy_month for full year."""
    return await _get_statement(db, fy_year, fy_month, Statement.is_)


@router.get(
    "/consolidated/bs",
    response_model=FinancialStatementResponse,
)
async def get_consolidated_bs(
    fy_year: int = Query(...),
    fy_month: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Consolidated Balance Sheet. Omit fy_month for full year."""
    return await _get_statement(db, fy_year, fy_month, Statement.bs)


async def _get_statement(
    db: AsyncSession,
    fy_year: int,
    fy_month: int | None,
    statement: Statement,
) -> FinancialStatementResponse:
    # ── Resolve periods ──────────────────────────────────────────────
    if fy_month is not None:
        # Single month selected → return that month + YTD
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month <= fy_month)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        target_period = next((p for p in all_periods if p.fy_month == fy_month), None)
        if target_period is None:
            raise HTTPException(status_code=404, detail="Period not found")
        period_ids = [p.id for p in all_periods]
        target_label = _period_label(target_period)
        column_labels = [target_label, "YTD"]
        period_id_to_label = {p.id: _period_label(p) for p in all_periods}
    else:
        # Full year → 12 monthly columns
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        if not all_periods:
            raise HTTPException(status_code=404, detail="No periods found for this FY")
        period_ids = [p.id for p in all_periods]
        column_labels = [_period_label(p) for p in all_periods]
        period_id_to_label = {p.id: _period_label(p) for p in all_periods}

    # ── Load accounts ────────────────────────────────────────────────
    result = await db.execute(
        select(Account)
        .where(Account.statement == statement)
        .order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())

    # ── Load actuals for all relevant periods ────────────────────────
    result = await db.execute(
        select(ConsolidatedActual).where(
            ConsolidatedActual.period_id.in_(period_ids),
        )
    )
    actuals = result.scalars().all()

    # ── Load entities ────────────────────────────────────────────────
    result = await db.execute(select(Entity))
    entities = {e.id: e for e in result.scalars().all()}

    # ── Index actuals by (account_id, period_label) ──────────────────
    # group_totals[account_id][period_label] = amount
    group_totals: dict[uuid.UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    # entity_amounts[account_id][entity_code][period_label] = amount
    entity_amounts: dict[uuid.UUID, dict[str, dict[str, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )

    for actual in actuals:
        label = period_id_to_label.get(actual.period_id)
        if label is None:
            continue
        if actual.is_group_total:
            group_totals[actual.account_id][label] += float(actual.amount)
        else:
            ent = entities.get(actual.entity_id)
            ecode = ent.code if ent else "?"
            entity_amounts[actual.account_id][ecode][label] += float(actual.amount)

    # ── Build rows ───────────────────────────────────────────────────
    rows_with_headers = _insert_section_headers(accounts, statement)
    rows: list[FinancialRow] = []

    for acct, section_header in rows_with_headers:
        if section_header is not None:
            rows.append(FinancialRow(
                account_code="",
                label=section_header,
                is_section_header=True,
            ))
            continue

        if fy_month is not None:
            # month + YTD columns
            target_label = column_labels[0]
            month_totals = group_totals.get(acct.id, {})
            ytd_sum = sum(month_totals.values())
            month_val = month_totals.get(target_label, 0.0)
            values = {target_label: month_val, "YTD": ytd_sum}

            # entity breakdown: same structure
            eb: dict[str, dict[str, float]] = {}
            for ecode, period_map in entity_amounts.get(acct.id, {}).items():
                eb[ecode] = {
                    target_label: period_map.get(target_label, 0.0),
                    "YTD": sum(period_map.values()),
                }
        else:
            # Full year columns
            month_totals = group_totals.get(acct.id, {})
            values = {lbl: month_totals.get(lbl, 0.0) for lbl in column_labels}

            eb = {}
            for ecode, period_map in entity_amounts.get(acct.id, {}).items():
                eb[ecode] = {lbl: period_map.get(lbl, 0.0) for lbl in column_labels}

        rows.append(FinancialRow(
            account_code=acct.code,
            label=acct.name,
            is_subtotal=acct.is_subtotal,
            indent_level=0 if acct.is_subtotal else 1,
            values=values,
            entity_breakdown=eb,
        ))

    return FinancialStatementResponse(periods=column_labels, rows=rows)
