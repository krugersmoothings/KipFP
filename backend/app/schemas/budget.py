import uuid
from datetime import datetime

from pydantic import BaseModel


# ── Budget version ────────────────────────────────────────────────────────────


class BudgetVersionRead(BaseModel):
    id: uuid.UUID
    name: str
    fy_year: int
    version_type: str
    status: str
    base_version_id: uuid.UUID | None = None
    created_by: uuid.UUID | None = None
    approved_by: uuid.UUID | None = None
    created_at: datetime
    locked_at: datetime | None = None

    model_config = {"from_attributes": True}


class BudgetVersionCreate(BaseModel):
    name: str
    fy_year: int
    version_type: str = "budget"
    base_version_id: uuid.UUID | None = None


# ── Calculation trigger / status ──────────────────────────────────────────────


class CalculationTriggerResponse(BaseModel):
    task_id: str
    status: str = "queued"


class CalculationStatusResponse(BaseModel):
    task_id: str | None = None
    status: str
    result: dict | None = None


# ── Model output ─────────────────────────────────────────────────────────────

class ModelOutputRow(BaseModel):
    account_code: str
    label: str
    is_subtotal: bool = False
    is_section_header: bool = False
    indent_level: int = 0
    values: dict[str, float] = {}
    entity_breakdown: dict[str, dict[str, float]] = {}


class ModelOutputResponse(BaseModel):
    version_id: uuid.UUID
    fy_year: int
    statement: str
    periods: list[str]
    rows: list[ModelOutputRow]


# ── Assumptions ───────────────────────────────────────────────────────────────


class ModelAssumptionRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID | None = None
    assumption_key: str
    assumption_value: dict
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssumptionPayload(BaseModel):
    entity_id: uuid.UUID | None = None
    assumption_key: str
    assumption_value: dict


# ── Working capital drivers ───────────────────────────────────────────────────


class WcDriverRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    account_id: uuid.UUID
    account_label: str = ""
    driver_type: str | None = None
    base_days: float | None = None
    seasonal_factors: dict | list | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class WcDriverUpdate(BaseModel):
    id: uuid.UUID
    base_days: float | None = None
    seasonal_factors: dict | list | None = None


# ── Debt ──────────────────────────────────────────────────────────────────────


class DebtScheduleRowRead(BaseModel):
    period_label: str
    opening_balance: float
    drawdown: float
    repayment: float
    closing_balance: float
    interest_expense: float
    interest_rate_applied: float


class DebtFacilityRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    entity_id: uuid.UUID
    facility_type: str | None = None
    opening_balance: float
    base_rate: float | None = None
    margin: float = 0
    amort_type: str | None = None
    monthly_repayment: float | None = None
    maturity_date: str | None = None
    is_active: bool = True
    schedule: list[DebtScheduleRowRead] = []

    model_config = {"from_attributes": True}


class DebtFacilityUpdate(BaseModel):
    base_rate: float | None = None
    margin: float = 0
    monthly_repayment: float | None = None


# ── Site budgets ──────────────────────────────────────────────────────────────


class SiteSummaryRead(BaseModel):
    location_id: uuid.UUID
    code: str
    name: str
    state: str | None = None
    entity_id: uuid.UUID | None = None
    capacity_dogs: int | None = None
    monthly_totals: dict[str, float] = {}


class SiteBudgetLineRead(BaseModel):
    line_item: str
    values: dict[str, float] = {}


class SiteBudgetGridRead(BaseModel):
    location_id: uuid.UUID
    location_name: str
    periods: list[str]
    lines: list[SiteBudgetLineRead]


class SiteBudgetLineSave(BaseModel):
    line_item: str
    values: dict[str, float] = {}


class SiteBudgetSavePayload(BaseModel):
    lines: list[SiteBudgetLineSave]


class SiteRollupRow(BaseModel):
    entity_code: str
    entity_name: str | None = None
    line_item: str
    site_total: dict[str, float] = {}
    model_assumption: dict[str, float] = {}
    variance: dict[str, float] = {}
