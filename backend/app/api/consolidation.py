import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_admin, require_finance
from app.db.models.account import Account, AccountType, NormalBalance, Statement
from app.db.models.budget import BudgetVersion, ModelOutput, VersionStatus, VersionType
from app.db.models.consolidation import ConsolidatedActual
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.user import User
from app.schemas.consolidation import (
    ConsolidationTriggerResponse,
    FinancialRow,
    FinancialStatementResponse,
)
from app.services.aasb16_helpers import compute_aasb16_per_period_with_entities

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


def _display_sign(account: Account, statement: Statement) -> float:
    """Return the multiplier to convert internal debit-positive amounts to
    presentation values.  IS accounts are all credit-normal (revenue stored
    negative) so we negate.  For BS, liabilities and equity are credit-normal
    and need negation; assets are debit-normal and stay as-is."""
    if statement == Statement.is_:
        return -1.0
    if account.normal_balance == NormalBalance.credit:
        return -1.0
    return 1.0


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
    include_aasb16: bool = Query(True),
    group_by: str | None = Query(None, description="'entity' for entity columns"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Consolidated Income Statement. Omit fy_month for full year."""
    if group_by == "entity":
        return await _get_statement_by_entity(db, fy_year, fy_month, Statement.is_, include_aasb16)
    return await _get_statement(db, fy_year, fy_month, Statement.is_, include_aasb16)


@router.get(
    "/consolidated/bs",
    response_model=FinancialStatementResponse,
)
async def get_consolidated_bs(
    fy_year: int = Query(...),
    fy_month: int | None = Query(None),
    include_aasb16: bool = Query(True),
    group_by: str | None = Query(None, description="'entity' for entity columns"),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Consolidated Balance Sheet. Omit fy_month for full year."""
    if group_by == "entity":
        return await _get_statement_by_entity(db, fy_year, fy_month, Statement.bs, include_aasb16)
    return await _get_statement(db, fy_year, fy_month, Statement.bs, include_aasb16)


async def _find_budget_version(
    db: AsyncSession,
    fy_year: int,
) -> BudgetVersion | None:
    """Find the best budget version: prefer approved, then any budget-type."""
    result = await db.execute(
        select(BudgetVersion).where(
            BudgetVersion.fy_year == fy_year,
            BudgetVersion.version_type == VersionType.budget,
            BudgetVersion.status == VersionStatus.approved,
        ).limit(1)
    )
    version = result.scalar_one_or_none()
    if version:
        return version
    result = await db.execute(
        select(BudgetVersion).where(
            BudgetVersion.fy_year == fy_year,
            BudgetVersion.version_type == VersionType.budget,
        ).order_by(BudgetVersion.created_at.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def _get_statement(
    db: AsyncSession,
    fy_year: int,
    fy_month: int | None,
    statement: Statement,
    include_aasb16: bool = True,
) -> FinancialStatementResponse:
    if statement == Statement.bs:
        return await _get_bs_statement(db, fy_year, fy_month, include_aasb16)

    # ── IS path ──────────────────────────────────────────────────────
    # ── Resolve periods (exclude fy_month=0 opening-balance periods) ─
    max_month = fy_month if fy_month is not None else 12
    result = await db.execute(
        select(Period)
        .where(
            Period.fy_year == fy_year,
            Period.fy_month >= 1,
            Period.fy_month <= max_month,
        )
        .order_by(Period.fy_month)
    )
    all_periods = list(result.scalars().all())
    if not all_periods:
        raise HTTPException(status_code=404, detail="No periods found for this FY")
    period_ids = [p.id for p in all_periods]
    month_labels = [_period_label(p) for p in all_periods]
    period_id_to_label = {p.id: _period_label(p) for p in all_periods}

    # ── Load accounts ────────────────────────────────────────────────
    result = await db.execute(
        select(Account)
        .where(Account.statement == statement)
        .order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())
    account_ids = [a.id for a in accounts]

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
    group_totals: dict[uuid.UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
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

    # ── AASB16 adjustment (ex-lease view) ────────────────────────────
    if not include_aasb16:
        aasb16_adj = await compute_aasb16_per_period_with_entities(db, period_ids, period_id_to_label)
        for acct_id, period_map in aasb16_adj.items():
            for label, amount in period_map.get("group", {}).items():
                group_totals[acct_id][label] -= amount
            for ecode, label_map in period_map.get("entities", {}).items():
                for label, amount in label_map.items():
                    entity_amounts[acct_id][ecode][label] -= amount

    # ── Load budget data for YTD Budget column ───────────────────────
    budget_totals: dict[uuid.UUID, float] = defaultdict(float)
    has_budget = False

    budget_version = await _find_budget_version(db, fy_year)
    if budget_version is not None:
        result = await db.execute(
            select(ModelOutput).where(
                ModelOutput.version_id == budget_version.id,
                ModelOutput.period_id.in_(period_ids),
                ModelOutput.account_id.in_(account_ids),
                ModelOutput.entity_id.is_(None),
            )
        )
        for mo in result.scalars().all():
            budget_totals[mo.account_id] += float(mo.amount)
            has_budget = True

    # ── Column layout: months + YTD + YTD Budget + Var % ─────────────
    column_labels = list(month_labels) + ["YTD"]
    if has_budget:
        column_labels += ["YTD Budget", "Var %"]

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

        sign = _display_sign(acct, statement)
        month_data = group_totals.get(acct.id, {})

        values: dict[str, float] = {}
        for lbl in month_labels:
            values[lbl] = month_data.get(lbl, 0.0) * sign

        ytd = sum(month_data.values()) * sign
        values["YTD"] = ytd

        if has_budget:
            ytd_budget = budget_totals.get(acct.id, 0.0) * sign
            values["YTD Budget"] = ytd_budget
            if ytd_budget != 0:
                values["Var %"] = (ytd - ytd_budget) / abs(ytd_budget) * 100
            else:
                values["Var %"] = 0.0

        eb: dict[str, dict[str, float]] = {}
        for ecode, period_map in entity_amounts.get(acct.id, {}).items():
            eb_vals: dict[str, float] = {}
            for lbl in month_labels:
                eb_vals[lbl] = period_map.get(lbl, 0.0) * sign
            eb_vals["YTD"] = sum(period_map.values()) * sign
            eb[ecode] = eb_vals

        rows.append(FinancialRow(
            account_code=acct.code,
            label=acct.name,
            is_subtotal=acct.is_subtotal,
            indent_level=0 if acct.is_subtotal else 1,
            values=values,
            entity_breakdown=eb,
        ))

    return FinancialStatementResponse(periods=column_labels, rows=rows)


# ── Balance-sheet specific helpers ────────────────────────────────────────

def _period_sort_key(p: Period) -> tuple[int, int]:
    """Sort key that orders periods chronologically (fy_month=0 before month 1)."""
    return (p.fy_year, p.fy_month)


async def _load_all_periods_through(
    db: AsyncSession,
    fy_year: int,
    fy_month: int | None,
) -> list[Period]:
    """Load every period from the earliest in the DB through the requested point.

    Includes opening-balance periods (fy_month=0).  Returns them sorted
    chronologically.
    """
    if fy_month is not None:
        q = select(Period).where(
            (Period.fy_year < fy_year)
            | ((Period.fy_year == fy_year) & (Period.fy_month <= fy_month))
        )
    else:
        q = select(Period).where(Period.fy_year <= fy_year)
    result = await db.execute(q.order_by(Period.fy_year, Period.fy_month))
    return list(result.scalars().all())


async def _get_bs_statement(
    db: AsyncSession,
    fy_year: int,
    fy_month: int | None,
    include_aasb16: bool = True,
) -> FinancialStatementResponse:
    """Consolidated Balance Sheet showing cumulative point-in-time balances.

    For a single-month view the columns are ``[<month>, "Balance"]`` where
    *month* is the month's movement and *Balance* is the cumulative balance
    at month-end.  For the full-year view each column is the cumulative
    balance at that month-end.
    """
    # ── Display periods (the columns the user sees) ───────────────────
    if fy_month is not None:
        result = await db.execute(
            select(Period).where(
                Period.fy_year == fy_year,
                Period.fy_month == fy_month,
            )
        )
        target_period = result.scalar_one_or_none()
        if target_period is None:
            raise HTTPException(status_code=404, detail="Period not found")
        target_label = _period_label(target_period)
        column_labels = [target_label, "Balance"]
    else:
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month >= 1)
            .order_by(Period.fy_month)
        )
        display_periods = list(result.scalars().all())
        if not display_periods:
            raise HTTPException(status_code=404, detail="No periods found for this FY")
        column_labels = [_period_label(p) for p in display_periods]

    # ── Load ALL historical periods through the requested endpoint ────
    all_periods = await _load_all_periods_through(db, fy_year, fy_month)
    all_period_ids = [p.id for p in all_periods]
    if not all_period_ids:
        raise HTTPException(status_code=404, detail="No periods found")

    # ── Load accounts ────────────────────────────────────────────────
    result = await db.execute(
        select(Account)
        .where(Account.statement == Statement.bs)
        .order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())

    # ── Load actuals across all historical periods ────────────────────
    result = await db.execute(
        select(ConsolidatedActual).where(
            ConsolidatedActual.period_id.in_(all_period_ids),
        )
    )
    actuals = result.scalars().all()

    # ── Load entities ────────────────────────────────────────────────
    result = await db.execute(select(Entity))
    entities = {e.id: e for e in result.scalars().all()}

    # ── Index actuals by (account_id, period_id) ─────────────────────
    # group_by_period[account_id][period_id] = amount
    group_by_period: dict[uuid.UUID, dict[uuid.UUID, float]] = defaultdict(
        lambda: defaultdict(float)
    )
    entity_by_period: dict[uuid.UUID, dict[str, dict[uuid.UUID, float]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(float))
    )

    for actual in actuals:
        if actual.is_group_total:
            group_by_period[actual.account_id][actual.period_id] += float(actual.amount)
        else:
            ent = entities.get(actual.entity_id)
            ecode = ent.code if ent else "?"
            entity_by_period[actual.account_id][ecode][actual.period_id] += float(actual.amount)

    # ── AASB16 adjustment ────────────────────────────────────────────
    if not include_aasb16:
        from app.services.aasb16_helpers import compute_aasb16_by_account_period
        aasb16_adj = await compute_aasb16_by_account_period(db, all_period_ids)
        for acct_id, period_amounts in aasb16_adj.items():
            for pid, amount in period_amounts.items():
                group_by_period[acct_id][pid] -= amount

    # ── Compute cumulative balances ──────────────────────────────────
    # Sort periods chronologically and build a running total per account
    sorted_periods = sorted(all_periods, key=_period_sort_key)

    if fy_month is not None:
        # Single-month view: movement for the selected month + cumulative
        # balance through that month-end.
        target_pid = target_period.id
        rows_with_headers = _insert_section_headers(accounts, Statement.bs)
        rows: list[FinancialRow] = []

        for acct, section_header in rows_with_headers:
            if section_header is not None:
                rows.append(FinancialRow(
                    account_code="", label=section_header, is_section_header=True,
                ))
                continue

            sign = _display_sign(acct, Statement.bs)
            acct_periods = group_by_period.get(acct.id, {})

            cumulative = sum(acct_periods.get(p.id, 0.0) for p in sorted_periods)
            movement = acct_periods.get(target_pid, 0.0)

            values = {
                target_label: movement * sign,
                "Balance": cumulative * sign,
            }

            eb: dict[str, dict[str, float]] = {}
            for ecode, ent_periods in entity_by_period.get(acct.id, {}).items():
                ent_cum = sum(ent_periods.get(p.id, 0.0) for p in sorted_periods)
                ent_mov = ent_periods.get(target_pid, 0.0)
                eb[ecode] = {
                    target_label: ent_mov * sign,
                    "Balance": ent_cum * sign,
                }

            rows.append(FinancialRow(
                account_code=acct.code,
                label=acct.name,
                is_subtotal=acct.is_subtotal,
                indent_level=0 if acct.is_subtotal else 1,
                values=values,
                entity_breakdown=eb,
            ))

    else:
        # Full-year view: each column is the cumulative balance at that
        # month-end (running total through all historical periods).
        result2 = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month >= 1)
            .order_by(Period.fy_month)
        )
        display_periods = list(result2.scalars().all())

        # Pre-compute the set of period ids that come *before* each display
        # period so we can build the running total efficiently.
        # prior_sum[i] = sum of all periods up to and including display_periods[i]
        cumulative_pid_sets: list[list[uuid.UUID]] = []
        for dp in display_periods:
            pids = [
                p.id for p in sorted_periods
                if _period_sort_key(p) <= _period_sort_key(dp)
            ]
            cumulative_pid_sets.append(pids)

        rows_with_headers = _insert_section_headers(accounts, Statement.bs)
        rows = []

        for acct, section_header in rows_with_headers:
            if section_header is not None:
                rows.append(FinancialRow(
                    account_code="", label=section_header, is_section_header=True,
                ))
                continue

            sign = _display_sign(acct, Statement.bs)
            acct_periods = group_by_period.get(acct.id, {})

            values: dict[str, float] = {}
            for i, dp in enumerate(display_periods):
                lbl = _period_label(dp)
                cum = sum(acct_periods.get(pid, 0.0) for pid in cumulative_pid_sets[i])
                values[lbl] = cum * sign

            eb: dict[str, dict[str, float]] = {}
            for ecode, ent_periods in entity_by_period.get(acct.id, {}).items():
                eb_vals: dict[str, float] = {}
                for i, dp in enumerate(display_periods):
                    lbl = _period_label(dp)
                    cum = sum(ent_periods.get(pid, 0.0) for pid in cumulative_pid_sets[i])
                    eb_vals[lbl] = cum * sign
                eb[ecode] = eb_vals

            rows.append(FinancialRow(
                account_code=acct.code,
                label=acct.name,
                is_subtotal=acct.is_subtotal,
                indent_level=0 if acct.is_subtotal else 1,
                values=values,
                entity_breakdown=eb,
            ))

    return FinancialStatementResponse(periods=column_labels, rows=rows)


async def _get_statement_by_entity(
    db: AsyncSession,
    fy_year: int,
    fy_month: int | None,
    statement: Statement,
    include_aasb16: bool = True,
) -> FinancialStatementResponse:
    """Return statement with one column per entity + Eliminations + Total."""

    # ── Resolve periods ──────────────────────────────────────────────
    # For BS we need ALL historical periods to build cumulative balances.
    if statement == Statement.bs:
        all_periods = await _load_all_periods_through(db, fy_year, fy_month)
    elif fy_month is not None:
        result = await db.execute(
            select(Period)
            .where(
                Period.fy_year == fy_year,
                Period.fy_month >= 1,
                Period.fy_month <= fy_month,
            )
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
    else:
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month >= 1)
            .order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())

    if not all_periods:
        raise HTTPException(status_code=404, detail="No periods found")
    period_ids = [p.id for p in all_periods]

    # ── Load accounts ────────────────────────────────────────────────
    result = await db.execute(
        select(Account).where(Account.statement == statement).order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())

    # ── Load actuals ─────────────────────────────────────────────────
    result = await db.execute(
        select(ConsolidatedActual).where(ConsolidatedActual.period_id.in_(period_ids))
    )
    actuals = result.scalars().all()

    result = await db.execute(select(Entity).where(Entity.is_active.is_(True)).order_by(Entity.code))
    entities = list(result.scalars().all())
    entity_map = {e.id: e for e in entities}
    entity_codes = [e.code for e in entities]

    # ── Aggregate: {account_id: {entity_code: sum, "__group__": sum}} ─
    data: dict[uuid.UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for actual in actuals:
        if actual.is_group_total:
            data[actual.account_id]["__group__"] += float(actual.amount)
        elif actual.entity_id and actual.entity_id in entity_map:
            ecode = entity_map[actual.entity_id].code
            data[actual.account_id][ecode] += float(actual.amount)

    # ── AASB16 adjustment ────────────────────────────────────────────
    if not include_aasb16:
        from app.services.aasb16_helpers import compute_aasb16_by_account_period
        aasb16_adj = await compute_aasb16_by_account_period(db, period_ids)
        for acct_id, period_amounts in aasb16_adj.items():
            total_adj = sum(period_amounts.values())
            data[acct_id]["__group__"] -= total_adj

    column_labels = entity_codes + ["Eliminations", "Total"]

    # ── Build rows ───────────────────────────────────────────────────
    rows_with_headers = _insert_section_headers(accounts, statement)
    rows: list[FinancialRow] = []

    for acct, section_header in rows_with_headers:
        if section_header is not None:
            rows.append(FinancialRow(
                account_code="", label=section_header, is_section_header=True,
            ))
            continue

        sign = _display_sign(acct, statement)
        acct_data = data.get(acct.id, {})
        entity_sum = sum(acct_data.get(ec, 0.0) for ec in entity_codes)
        group_total = acct_data.get("__group__", 0.0)
        eliminations = group_total - entity_sum

        values: dict[str, float] = {}
        for ec in entity_codes:
            values[ec] = acct_data.get(ec, 0.0) * sign
        values["Eliminations"] = eliminations * sign
        values["Total"] = group_total * sign

        rows.append(FinancialRow(
            account_code=acct.code,
            label=acct.name,
            is_subtotal=acct.is_subtotal,
            indent_level=0 if acct.is_subtotal else 1,
            values=values,
            entity_breakdown={},
        ))

    return FinancialStatementResponse(periods=column_labels, rows=rows)


# ── Drill-down endpoint for a single cell ────────────────────────────────

@router.get(
    "/consolidated/drilldown",
    response_model=list,
)
async def get_drilldown(
    fy_year: int = Query(...),
    fy_month: int = Query(...),
    account_code: str = Query(...),
    include_aasb16: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Return entity-level breakdown for a single account + period cell."""
    result = await db.execute(
        select(Period).where(
            Period.fy_year == fy_year,
            Period.fy_month == fy_month,
        )
    )
    period = result.scalar_one_or_none()
    if period is None:
        raise HTTPException(status_code=404, detail="Period not found")

    result = await db.execute(
        select(Account).where(Account.code == account_code)
    )
    account = result.scalar_one_or_none()
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")

    sign = _display_sign(account, account.statement)

    result = await db.execute(
        select(ConsolidatedActual).where(
            ConsolidatedActual.period_id == period.id,
            ConsolidatedActual.account_id == account.id,
        )
    )
    actuals = result.scalars().all()

    result = await db.execute(select(Entity))
    entities = {e.id: e for e in result.scalars().all()}

    group_total = 0.0
    entity_rows: list[dict] = []
    entity_sum = 0.0

    for actual in actuals:
        if actual.is_group_total:
            group_total = float(actual.amount) * sign
        else:
            ent = entities.get(actual.entity_id)
            if ent:
                amt = float(actual.amount) * sign
                entity_sum += amt
                entity_rows.append({
                    "entity_id": str(ent.id),
                    "entity_code": ent.code,
                    "entity_name": ent.name or ent.code,
                    "amount": amt,
                    "source_entity_id": ent.source_entity_id,
                })

    eliminations = group_total - entity_sum
    if abs(eliminations) > 0.5:
        entity_rows.append({
            "entity_id": None,
            "entity_code": "ELIM",
            "entity_name": "Eliminations",
            "amount": eliminations,
            "source_entity_id": None,
        })

    entity_rows.sort(key=lambda r: (r["entity_code"] == "ELIM", r["entity_code"]))

    return entity_rows


@router.get(
    "/consolidated/is/blended",
    response_model=FinancialStatementResponse,
)
async def get_blended_is(
    fy_year: int = Query(...),
    last_actual_month: int = Query(..., description="FY month up to which actuals are used (1-12)"),
    version_id: uuid.UUID = Query(..., description="Budget/forecast version for months after last_actual_month"),
    include_aasb16: bool = Query(True),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Blended IS: actuals up to last_actual_month, forecast for remaining months."""
    result = await db.execute(
        select(Period)
        .where(Period.fy_year == fy_year, Period.fy_month >= 1)
        .order_by(Period.fy_month)
    )
    all_periods = list(result.scalars().all())
    if not all_periods:
        raise HTTPException(status_code=404, detail="No periods found")

    period_map = {p.fy_month: p for p in all_periods}
    column_labels = [_period_label(p) for p in all_periods]

    result = await db.execute(
        select(Account).where(Account.statement == Statement.is_).order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())
    account_ids = [a.id for a in accounts]

    actual_period_ids = [p.id for p in all_periods if p.fy_month <= last_actual_month]
    forecast_period_ids = [p.id for p in all_periods if p.fy_month > last_actual_month]

    actual_amounts: dict[uuid.UUID, dict[uuid.UUID, float]] = defaultdict(lambda: defaultdict(float))
    if actual_period_ids:
        result = await db.execute(
            select(ConsolidatedActual).where(
                ConsolidatedActual.period_id.in_(actual_period_ids),
                ConsolidatedActual.is_group_total.is_(True),
                ConsolidatedActual.account_id.in_(account_ids),
            )
        )
        for act in result.scalars().all():
            actual_amounts[act.account_id][act.period_id] += float(act.amount)

    if not include_aasb16 and actual_period_ids:
        from app.services.aasb16_helpers import compute_aasb16_by_account_period
        aasb16_adj = await compute_aasb16_by_account_period(db, actual_period_ids)
        for acct_id in account_ids:
            if acct_id in aasb16_adj:
                for pid in actual_period_ids:
                    actual_amounts[acct_id][pid] -= aasb16_adj[acct_id].get(pid, 0.0)

    forecast_amounts: dict[uuid.UUID, dict[uuid.UUID, float]] = defaultdict(lambda: defaultdict(float))
    if forecast_period_ids:
        result = await db.execute(
            select(ModelOutput).where(
                ModelOutput.version_id == version_id,
                ModelOutput.period_id.in_(forecast_period_ids),
                ModelOutput.account_id.in_(account_ids),
                ModelOutput.entity_id.is_(None),
            )
        )
        for mo in result.scalars().all():
            forecast_amounts[mo.account_id][mo.period_id] += float(mo.amount)

    rows_with_headers = _insert_section_headers(accounts, Statement.is_)
    rows: list[FinancialRow] = []

    for acct, section_header in rows_with_headers:
        if section_header is not None:
            rows.append(FinancialRow(
                account_code="", label=section_header, is_section_header=True,
            ))
            continue

        values: dict[str, float] = {}
        for p in all_periods:
            lbl = _period_label(p)
            if p.fy_month <= last_actual_month:
                val = actual_amounts[acct.id].get(p.id, 0.0)
            else:
                val = forecast_amounts[acct.id].get(p.id, 0.0)
            values[lbl] = val * -1.0

        rows.append(FinancialRow(
            account_code=acct.code,
            label=acct.name,
            is_subtotal=acct.is_subtotal,
            indent_level=0 if acct.is_subtotal else 1,
            values=values,
            entity_breakdown={},
        ))

    return FinancialStatementResponse(periods=column_labels, rows=rows)


# ── Blended Cash Flow ────────────────────────────────────────────────────

CF_CODES = ["CF-OPERATING", "CF-INVESTING", "CF-FINANCING", "CF-NET"]
CF_LABELS = {
    "CF-OPERATING": "Operating Cash Flow",
    "CF-INVESTING": "Investing Cash Flow",
    "CF-FINANCING": "Financing Cash Flow",
    "CF-NET": "Net Cash Flow",
}
CASH_CODE = "BS-CASH"


@router.get(
    "/consolidated/cf/blended",
    response_model=FinancialStatementResponse,
)
async def get_blended_cf(
    fy_year: int = Query(...),
    last_actual_month: int = Query(
        ..., description="FY month up to which actuals are used (1-12)"
    ),
    version_id: uuid.UUID = Query(
        ..., description="Budget/forecast version for months after last_actual_month"
    ),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    """Blended Cash Flow: actual cash balance for closed months, forecast CF
    breakdown + cash balance for future months."""

    # ── Resolve periods ──────────────────────────────────────────────
    result = await db.execute(
        select(Period)
        .where(Period.fy_year == fy_year, Period.fy_month >= 1)
        .order_by(Period.fy_month)
    )
    all_periods = list(result.scalars().all())
    if not all_periods:
        raise HTTPException(status_code=404, detail="No periods found")

    column_labels = [_period_label(p) for p in all_periods]

    # ── Load CF + Cash accounts ──────────────────────────────────────
    result = await db.execute(
        select(Account).where(
            Account.code.in_(CF_CODES + [CASH_CODE])
        )
    )
    accounts_by_code: dict[str, Account] = {a.code: a for a in result.scalars().all()}

    forecast_period_ids = [p.id for p in all_periods if p.fy_month > last_actual_month]

    # ── Actual BS-CASH from ConsolidatedActual ───────────────────────
    all_historical = await _load_all_periods_through(db, fy_year, last_actual_month)
    all_historical_ids = [p.id for p in all_historical]
    sorted_historical = sorted(all_historical, key=_period_sort_key)

    cash_account = accounts_by_code.get(CASH_CODE)
    actual_cash_by_period: dict[str, float] = {}

    if cash_account and all_historical_ids:
        result = await db.execute(
            select(ConsolidatedActual).where(
                ConsolidatedActual.account_id == cash_account.id,
                ConsolidatedActual.period_id.in_(all_historical_ids),
                ConsolidatedActual.is_group_total.is_(True),
            )
        )
        cash_movements: dict[uuid.UUID, float] = {}
        for act in result.scalars().all():
            cash_movements[act.period_id] = float(act.amount)

        for dp in all_periods:
            if dp.fy_month > last_actual_month:
                break
            cum = sum(
                cash_movements.get(p.id, 0.0)
                for p in sorted_historical
                if _period_sort_key(p) <= _period_sort_key(dp)
            )
            # BS-CASH is debit-normal so positive = cash in hand
            actual_cash_by_period[_period_label(dp)] = cum

    # ── Derive actual net CF from cash balance deltas ────────────────
    actual_cf_net: dict[str, float] = {}
    prev_cash = 0.0
    for dp in all_periods:
        if dp.fy_month > last_actual_month:
            break
        lbl = _period_label(dp)
        curr_cash = actual_cash_by_period.get(lbl, 0.0)
        actual_cf_net[lbl] = curr_cash - prev_cash
        prev_cash = curr_cash

    # ── Forecast CF + Cash from ModelOutput ──────────────────────────
    forecast_amounts: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    if forecast_period_ids:
        cf_account_ids = [
            a.id for code, a in accounts_by_code.items()
            if code in CF_CODES or code == CASH_CODE
        ]
        if cf_account_ids:
            result = await db.execute(
                select(ModelOutput).where(
                    ModelOutput.version_id == version_id,
                    ModelOutput.period_id.in_(forecast_period_ids),
                    ModelOutput.account_id.in_(cf_account_ids),
                    ModelOutput.entity_id.is_(None),
                )
            )
            id_to_code = {a.id: code for code, a in accounts_by_code.items()}
            period_id_to_label = {p.id: _period_label(p) for p in all_periods}
            for mo in result.scalars().all():
                code = id_to_code.get(mo.account_id, "")
                lbl = period_id_to_label.get(mo.period_id, "")
                if code and lbl:
                    forecast_amounts[code][lbl] += float(mo.amount)

    # ── Build rows ───────────────────────────────────────────────────
    rows: list[FinancialRow] = []

    rows.append(FinancialRow(
        account_code="", label="Cash Flow", is_section_header=True,
    ))

    for cf_code in CF_CODES:
        values: dict[str, float] = {}
        for p in all_periods:
            lbl = _period_label(p)
            if p.fy_month <= last_actual_month:
                if cf_code == "CF-NET":
                    values[lbl] = actual_cf_net.get(lbl, 0.0)
                else:
                    values[lbl] = 0.0
            else:
                values[lbl] = forecast_amounts.get(cf_code, {}).get(lbl, 0.0) * -1.0

        rows.append(FinancialRow(
            account_code=cf_code,
            label=CF_LABELS.get(cf_code, cf_code),
            is_subtotal=(cf_code == "CF-NET"),
            indent_level=0 if cf_code == "CF-NET" else 1,
            values=values,
            entity_breakdown={},
        ))

    rows.append(FinancialRow(
        account_code="", label="Cash Balance", is_section_header=True,
    ))

    cash_values: dict[str, float] = {}
    for p in all_periods:
        lbl = _period_label(p)
        if p.fy_month <= last_actual_month:
            cash_values[lbl] = actual_cash_by_period.get(lbl, 0.0)
        else:
            cash_values[lbl] = forecast_amounts.get(CASH_CODE, {}).get(lbl, 0.0) * -1.0

    rows.append(FinancialRow(
        account_code=CASH_CODE,
        label="Closing Cash Balance",
        is_subtotal=True,
        indent_level=0,
        values=cash_values,
        entity_breakdown={},
    ))

    return FinancialStatementResponse(periods=column_labels, rows=rows)
