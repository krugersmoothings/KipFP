import uuid
from datetime import datetime

from pydantic import BaseModel


class ConsolidationTriggerResponse(BaseModel):
    consolidation_run_id: uuid.UUID
    status: str = "queued"


class ConsolidationRunRead(BaseModel):
    id: uuid.UUID
    period_id: uuid.UUID
    status: str
    bs_balanced: bool | None = None
    bs_variance: float | None = None
    ic_alerts: str | None = None
    error_detail: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    model_config = {"from_attributes": True}


class EntityBreakdown(BaseModel):
    entity_id: uuid.UUID
    entity_code: str
    amount: float


class ConsolidatedLineItem(BaseModel):
    account_code: str
    account_name: str
    amount: float
    is_subtotal: bool = False
    entity_breakdown: list[EntityBreakdown] = []


# ── Multi-period financial statement response ────────────────────────────


class FinancialRow(BaseModel):
    account_code: str
    label: str
    is_subtotal: bool = False
    is_section_header: bool = False
    indent_level: int = 0
    values: dict[str, float] = {}
    entity_breakdown: dict[str, dict[str, float]] = {}


class FinancialStatementResponse(BaseModel):
    periods: list[str]
    rows: list[FinancialRow]


# ── Dashboard KPIs ───────────────────────────────────────────────────────


class DashboardKPIs(BaseModel):
    revenue_mtd: float = 0
    revenue_pcp: float = 0
    gm_pct: float | None = None
    gm_pct_pcp: float | None = None
    ebitda_mtd: float = 0
    ebitda_ytd: float = 0
    net_cash: float = 0
    total_debt: float = 0
    last_sync_at: datetime | None = None
