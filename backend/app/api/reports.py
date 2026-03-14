"""Variance reporting and Excel/PDF export."""

from __future__ import annotations

import io
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_finance
from app.db.models.account import Account, AccountType, Statement
from app.db.models.budget import BudgetVersion, ModelOutput, ReportCommentary
from app.db.models.consolidation import ConsolidatedActual
from app.db.models.entity import Entity
from app.db.models.period import Period
from app.db.models.user import User
from app.schemas.reports import (
    CommentaryPayload,
    CommentaryRead,
    ExportRequest,
    VarianceReportResponse,
    VarianceRow,
)

router = APIRouter(prefix="/reports", tags=["reports"])

MONTH_ABBR = [
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
]

IS_SECTIONS: dict[str, list[AccountType]] = {
    "Revenue": [AccountType.income, AccountType.cogs],
    "Operating Expenses": [AccountType.opex],
    "Depreciation & Amortisation": [AccountType.depreciation],
    "Interest": [AccountType.interest],
    "Tax": [AccountType.tax],
}

EXPENSE_TYPES = {AccountType.cogs, AccountType.opex, AccountType.depreciation, AccountType.tax}


def _period_label(period: Period) -> str:
    if period.period_start:
        return period.period_start.strftime("%b-%y")
    cal_year = period.fy_year - 1 if period.fy_month <= 6 else period.fy_year
    return f"{MONTH_ABBR[period.fy_month - 1]}-{cal_year % 100:02d}"


def _is_expense(acct: Account) -> bool:
    return acct.account_type in EXPENSE_TYPES


def _compute_variance(actual: float, budget: float, is_expense: bool) -> tuple[float, float | None, bool | None]:
    var_abs = actual - budget
    var_pct = (var_abs / budget * 100) if budget != 0 else None
    if budget == 0 and actual == 0:
        is_fav = None
    elif is_expense:
        is_fav = actual < budget
    else:
        is_fav = actual > budget
    return var_abs, var_pct, is_fav


# ── GET /reports/variance ────────────────────────────────────────────────────


@router.get("/variance", response_model=VarianceReportResponse)
async def get_variance_report(
    fy_year: int = Query(...),
    fy_month: int | None = Query(None, description="Omit or pass 0 for YTD; -1 for full year"),
    version_id: uuid.UUID = Query(...),
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    version = await db.get(BudgetVersion, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Budget version not found")

    # Determine view mode and periods
    if fy_month is not None and fy_month > 0:
        view_mode = "monthly"
        result = await db.execute(
            select(Period)
            .where(Period.fy_year == fy_year, Period.fy_month == fy_month)
        )
        target_period = result.scalar_one_or_none()
        if target_period is None:
            raise HTTPException(status_code=404, detail="Period not found")
        period_ids = [target_period.id]
        period_label = _period_label(target_period)
    elif fy_month is not None and fy_month == -1:
        view_mode = "full_year"
        result = await db.execute(
            select(Period).where(Period.fy_year == fy_year).order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        period_ids = [p.id for p in all_periods]
        period_label = f"FY{fy_year} Full Year"
    else:
        view_mode = "ytd"
        result = await db.execute(
            select(Period).where(Period.fy_year == fy_year).order_by(Period.fy_month)
        )
        all_periods = list(result.scalars().all())
        period_ids = [p.id for p in all_periods]
        period_label = f"FY{fy_year} YTD"

    # Load prior year periods for PCP comparison
    prior_fy = fy_year - 1
    if view_mode == "monthly" and fy_month:
        pcp_result = await db.execute(
            select(Period).where(Period.fy_year == prior_fy, Period.fy_month == fy_month)
        )
        pcp_periods = list(pcp_result.scalars().all())
    else:
        pcp_result = await db.execute(
            select(Period).where(Period.fy_year == prior_fy).order_by(Period.fy_month)
        )
        pcp_periods = list(pcp_result.scalars().all())
    pcp_period_ids = [p.id for p in pcp_periods]

    # Load IS accounts
    result = await db.execute(
        select(Account)
        .where(Account.statement == Statement.is_)
        .order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())
    account_ids = [a.id for a in accounts]

    # Load actuals (current year)
    actual_totals: dict[uuid.UUID, float] = defaultdict(float)
    if period_ids:
        result = await db.execute(
            select(ConsolidatedActual).where(
                ConsolidatedActual.period_id.in_(period_ids),
                ConsolidatedActual.is_group_total.is_(True),
                ConsolidatedActual.account_id.in_(account_ids),
            )
        )
        for act in result.scalars().all():
            actual_totals[act.account_id] += float(act.amount)

    # Load budget outputs
    budget_totals: dict[uuid.UUID, float] = defaultdict(float)
    if period_ids:
        result = await db.execute(
            select(ModelOutput).where(
                ModelOutput.version_id == version_id,
                ModelOutput.period_id.in_(period_ids),
                ModelOutput.account_id.in_(account_ids),
                ModelOutput.entity_id.is_(None),
            )
        )
        for mo in result.scalars().all():
            budget_totals[mo.account_id] += float(mo.amount)

    # Load prior year actuals
    pcp_totals: dict[uuid.UUID, float] = defaultdict(float)
    if pcp_period_ids:
        result = await db.execute(
            select(ConsolidatedActual).where(
                ConsolidatedActual.period_id.in_(pcp_period_ids),
                ConsolidatedActual.is_group_total.is_(True),
                ConsolidatedActual.account_id.in_(account_ids),
            )
        )
        for act in result.scalars().all():
            pcp_totals[act.account_id] += float(act.amount)

    # Load commentary (keyed by version + account, period_id always NULL)
    commentary_map: dict[uuid.UUID, str] = {}
    result = await db.execute(
        select(ReportCommentary).where(
            ReportCommentary.version_id == version_id,
            ReportCommentary.period_id.is_(None),
        )
    )
    for c in result.scalars().all():
        commentary_map[c.account_id] = c.comment or ""

    # Build rows with section headers
    type_to_section: dict[AccountType, str] = {}
    for sec, types in IS_SECTIONS.items():
        for t in types:
            type_to_section[t] = sec

    rows: list[VarianceRow] = []
    seen_sections: set[str] = set()

    for acct in accounts:
        sec = type_to_section.get(acct.account_type)
        if sec and sec not in seen_sections:
            seen_sections.add(sec)
            rows.append(VarianceRow(
                account_code="",
                label=sec,
                is_section_header=True,
            ))

        actual = actual_totals.get(acct.id, 0.0)
        budget = budget_totals.get(acct.id, 0.0)
        pcp = pcp_totals.get(acct.id, 0.0)
        expense = _is_expense(acct)

        var_abs, var_pct, is_fav = _compute_variance(actual, budget, expense)
        pcp_abs = actual - pcp
        pcp_pct = (pcp_abs / pcp * 100) if pcp != 0 else None

        rows.append(VarianceRow(
            account_id=acct.id,
            account_code=acct.code,
            label=acct.name,
            is_subtotal=acct.is_subtotal,
            indent_level=0 if acct.is_subtotal else 1,
            actual=actual,
            budget=budget,
            variance_abs=var_abs,
            variance_pct=var_pct,
            is_favourable=is_fav,
            prior_year_actual=pcp,
            vs_pcp_abs=pcp_abs,
            vs_pcp_pct=pcp_pct,
            commentary=commentary_map.get(acct.id),
        ))

    return VarianceReportResponse(
        fy_year=fy_year,
        period_label=period_label,
        version_id=version_id,
        view_mode=view_mode,
        rows=rows,
    )


# ── PUT /reports/commentary ──────────────────────────────────────────────────


@router.put("/commentary", response_model=CommentaryRead)
async def save_commentary(
    payload: CommentaryPayload,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_finance),
):
    period_filter = (
        ReportCommentary.period_id == payload.period_id
        if payload.period_id is not None
        else ReportCommentary.period_id.is_(None)
    )
    result = await db.execute(
        select(ReportCommentary).where(
            ReportCommentary.version_id == payload.version_id,
            ReportCommentary.account_id == payload.account_id,
            period_filter,
        )
    )
    existing = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if existing:
        existing.comment = payload.comment
        existing.updated_by = user.id
        existing.updated_at = now
        await db.commit()
        await db.refresh(existing)
        return existing
    else:
        entry = ReportCommentary(
            version_id=payload.version_id,
            account_id=payload.account_id,
            period_id=payload.period_id,
            comment=payload.comment,
            updated_by=user.id,
            updated_at=now,
        )
        db.add(entry)
        await db.commit()
        await db.refresh(entry)
        return entry


# ── POST /reports/export ─────────────────────────────────────────────────────


@router.post("/export")
async def export_report(
    payload: ExportRequest,
    db: AsyncSession = Depends(get_db),
    _user: User = Depends(require_finance),
):
    if payload.format != "xlsx":
        raise HTTPException(status_code=400, detail="Only xlsx format is currently supported")

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side, numbers
    except ImportError:
        raise HTTPException(status_code=500, detail="openpyxl not installed")

    NAVY = "1F3D6E"
    header_font = Font(color="FFFFFF", bold=True, size=11)
    header_fill = PatternFill(start_color=NAVY, end_color=NAVY, fill_type="solid")
    subtotal_font = Font(bold=True, size=11)
    number_fmt = "#,##0"
    pct_fmt = "0.0%"
    thin_border = Border(bottom=Side(style="thin", color="CCCCCC"))

    # Load periods
    result = await db.execute(
        select(Period).where(Period.fy_year == payload.fy_year).order_by(Period.fy_month)
    )
    periods = list(result.scalars().all())
    period_ids = [p.id for p in periods]
    period_labels = [_period_label(p) for p in periods]

    wb = Workbook()
    wb.remove(wb.active)

    if payload.type == "variance" and payload.version_id:
        await _export_variance_sheets(
            wb, db, payload.version_id, payload.fy_year, periods, period_ids, period_labels,
            header_font, header_fill, subtotal_font, number_fmt, pct_fmt, thin_border,
        )
    elif payload.type == "budget" and payload.version_id:
        for stmt, stmt_label in [("is", "Income Statement"), ("bs", "Balance Sheet"), ("cf", "Cash Flow")]:
            await _export_budget_sheet(
                wb, db, payload.version_id, stmt, stmt_label,
                periods, period_ids, period_labels,
                header_font, header_fill, subtotal_font, number_fmt, thin_border,
            )
    elif payload.type == "actuals":
        for stmt, stmt_label in [("is", "Income Statement"), ("bs", "Balance Sheet")]:
            await _export_actuals_sheet(
                wb, db, stmt, stmt_label, period_ids, period_labels,
                header_font, header_fill, subtotal_font, number_fmt, thin_border,
            )
    else:
        raise HTTPException(status_code=400, detail="Invalid export type or missing version_id")

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    filename = f"kip_{payload.type}_FY{payload.fy_year}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _export_variance_sheets(wb, db, version_id, fy_year, periods, period_ids, period_labels,
                                  header_font, header_fill, subtotal_font, number_fmt, pct_fmt, thin_border):
    from openpyxl.styles import Alignment

    result = await db.execute(
        select(Account).where(Account.statement == Statement.is_).order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())
    account_ids = [a.id for a in accounts]

    actual_by_acct: dict[uuid.UUID, float] = defaultdict(float)
    result = await db.execute(
        select(ConsolidatedActual).where(
            ConsolidatedActual.period_id.in_(period_ids),
            ConsolidatedActual.is_group_total.is_(True),
            ConsolidatedActual.account_id.in_(account_ids),
        )
    )
    for act in result.scalars().all():
        actual_by_acct[act.account_id] += float(act.amount)

    budget_by_acct: dict[uuid.UUID, float] = defaultdict(float)
    result = await db.execute(
        select(ModelOutput).where(
            ModelOutput.version_id == version_id,
            ModelOutput.period_id.in_(period_ids),
            ModelOutput.account_id.in_(account_ids),
            ModelOutput.entity_id.is_(None),
        )
    )
    for mo in result.scalars().all():
        budget_by_acct[mo.account_id] += float(mo.amount)

    ws = wb.create_sheet(title="IS Variance")
    headers = ["Account", "Actual", "Budget", "Variance $", "Variance %"]
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 40
    for c in ["B", "C", "D", "E"]:
        ws.column_dimensions[c].width = 14

    row_idx = 2
    for acct in accounts:
        actual = actual_by_acct.get(acct.id, 0)
        budget = budget_by_acct.get(acct.id, 0)
        var = actual - budget
        var_pct = var / budget if budget != 0 else 0

        ws.cell(row=row_idx, column=1, value=f"{'  ' if not acct.is_subtotal else ''}{acct.name}")
        c_actual = ws.cell(row=row_idx, column=2, value=round(actual, 2))
        c_budget = ws.cell(row=row_idx, column=3, value=round(budget, 2))
        c_var = ws.cell(row=row_idx, column=4, value=round(var, 2))
        c_pct = ws.cell(row=row_idx, column=5, value=round(var_pct, 4))

        c_actual.number_format = number_fmt
        c_budget.number_format = number_fmt
        c_var.number_format = number_fmt
        c_pct.number_format = pct_fmt

        if acct.is_subtotal:
            for col in range(1, 6):
                ws.cell(row=row_idx, column=col).font = subtotal_font
                ws.cell(row=row_idx, column=col).border = thin_border

        row_idx += 1


async def _export_budget_sheet(wb, db, version_id, stmt_key, stmt_label,
                               periods, period_ids, period_labels,
                               header_font, header_fill, subtotal_font, number_fmt, thin_border):
    from openpyxl.styles import Alignment

    statement = Statement.is_ if stmt_key == "is" else (Statement.bs if stmt_key == "bs" else Statement.cf)

    if statement == Statement.cf:
        cf_codes = ["CF-OPERATING", "CF-INVESTING", "CF-FINANCING", "CF-NET"]
        result = await db.execute(select(Account).where(Account.code.in_(cf_codes)))
        accounts = list(result.scalars().all())
    else:
        result = await db.execute(
            select(Account).where(Account.statement == statement).order_by(Account.sort_order)
        )
        accounts = list(result.scalars().all())

    account_ids = [a.id for a in accounts]
    amounts: dict[tuple[uuid.UUID, uuid.UUID], float] = {}
    result = await db.execute(
        select(ModelOutput).where(
            ModelOutput.version_id == version_id,
            ModelOutput.period_id.in_(period_ids),
            ModelOutput.account_id.in_(account_ids),
            ModelOutput.entity_id.is_(None),
        )
    )
    for mo in result.scalars().all():
        amounts[(mo.account_id, mo.period_id)] = float(mo.amount)

    ws = wb.create_sheet(title=stmt_label)
    headers = ["Account"] + period_labels
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 40
    for i in range(len(period_labels)):
        ws.column_dimensions[chr(66 + i)].width = 12

    row_idx = 2
    for acct in accounts:
        ws.cell(row=row_idx, column=1, value=f"{'  ' if not acct.is_subtotal else ''}{acct.name}")
        for pi, period in enumerate(periods):
            val = amounts.get((acct.id, period.id), 0)
            c = ws.cell(row=row_idx, column=2 + pi, value=round(val, 2))
            c.number_format = number_fmt
        if acct.is_subtotal:
            for col in range(1, 2 + len(periods)):
                ws.cell(row=row_idx, column=col).font = subtotal_font
                ws.cell(row=row_idx, column=col).border = thin_border
        row_idx += 1


async def _export_actuals_sheet(wb, db, stmt_key, stmt_label, period_ids, period_labels,
                                header_font, header_fill, subtotal_font, number_fmt, thin_border):
    from openpyxl.styles import Alignment

    statement = Statement.is_ if stmt_key == "is" else Statement.bs
    result = await db.execute(
        select(Account).where(Account.statement == statement).order_by(Account.sort_order)
    )
    accounts = list(result.scalars().all())
    account_ids = [a.id for a in accounts]

    amounts: dict[tuple[uuid.UUID, uuid.UUID], float] = {}
    result = await db.execute(
        select(ConsolidatedActual).where(
            ConsolidatedActual.period_id.in_(period_ids),
            ConsolidatedActual.is_group_total.is_(True),
            ConsolidatedActual.account_id.in_(account_ids),
        )
    )
    for act in result.scalars().all():
        amounts[(act.account_id, act.period_id)] = float(act.amount)

    ws = wb.create_sheet(title=stmt_label)
    headers = ["Account"] + period_labels
    for col, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = Alignment(horizontal="center")
    ws.column_dimensions["A"].width = 40
    for i in range(len(period_labels)):
        ws.column_dimensions[chr(66 + i)].width = 12

    row_idx = 2
    for acct in accounts:
        ws.cell(row=row_idx, column=1, value=f"{'  ' if not acct.is_subtotal else ''}{acct.name}")
        for pi, pid in enumerate(period_ids):
            val = amounts.get((acct.id, pid), 0)
            c = ws.cell(row=row_idx, column=2 + pi, value=round(val, 2))
            c.number_format = number_fmt
        if acct.is_subtotal:
            for col in range(1, 2 + len(period_ids)):
                ws.cell(row=row_idx, column=col).font = subtotal_font
                ws.cell(row=row_idx, column=col).border = thin_border
        row_idx += 1
