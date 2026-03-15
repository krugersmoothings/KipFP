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
    location_id: uuid.UUID | None = None
    assumption_key: str
    assumption_value: dict
    updated_at: datetime

    model_config = {"from_attributes": True}


class AssumptionPayload(BaseModel):
    entity_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None
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


class DebtHistoryPoint(BaseModel):
    period_label: str
    fy_year: int
    fy_month: int
    balance: float
    movement: float
    implied_monthly_amort: float | None = None


class DebtFacilityRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    entity_id: uuid.UUID
    entity_code: str | None = None
    facility_type: str | None = None
    opening_balance: float
    current_balance: float | None = None
    base_rate: float | None = None
    margin: float = 0
    amort_type: str | None = None
    monthly_repayment: float | None = None
    maturity_date: str | None = None
    is_active: bool = True
    schedule: list[DebtScheduleRowRead] = []
    history: list[DebtHistoryPoint] = []
    implied_interest_rate: float | None = None
    avg_monthly_repayment: float | None = None

    model_config = {"from_attributes": True}


class DebtFacilityUpdate(BaseModel):
    base_rate: float | None = None
    margin: float = 0
    monthly_repayment: float | None = None


class DebtSummary(BaseModel):
    total_debt: float = 0
    total_interest_budget: float = 0
    total_repayment_budget: float = 0
    facility_count: int = 0
    facilities: list[DebtFacilityRead] = []
    total_debt_history: list[DebtHistoryPoint] = []


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


# ── Site budget assumptions (operational budget engine) ──────────────────────


class SiteBudgetAssumptionRead(BaseModel):
    id: uuid.UUID
    version_id: uuid.UUID
    location_id: uuid.UUID
    fy_year: int
    price_growth_pct: float | None = None
    pet_day_growth_pct: float | None = None
    bath_price: float | None = None
    other_services_per_pet_day: float | None = None
    membership_pct_revenue: float | None = None
    mpp_mins: float | None = None
    min_daily_hours: float | None = None
    wage_increase_pct: float | None = None
    cogs_pct: float | None = None
    rent_monthly: float | None = None
    rent_growth_pct: float | None = None
    utilities_monthly: float | None = None
    utilities_growth_pct: float | None = None
    rm_monthly: float | None = None
    rm_growth_pct: float | None = None
    it_monthly: float | None = None
    it_growth_pct: float | None = None
    general_monthly: float | None = None
    general_growth_pct: float | None = None
    advertising_pct_revenue: float | None = None
    assumptions_locked: bool = False
    prior_year_avg_price: float | None = None
    prior_year_total_pet_days: int | None = None
    prior_year_avg_wage: float | None = None

    model_config = {"from_attributes": True}


class SiteBudgetAssumptionUpdate(BaseModel):
    price_growth_pct: float | None = None
    pet_day_growth_pct: float | None = None
    bath_price: float | None = None
    other_services_per_pet_day: float | None = None
    membership_pct_revenue: float | None = None
    mpp_mins: float | None = None
    min_daily_hours: float | None = None
    wage_increase_pct: float | None = None
    cogs_pct: float | None = None
    rent_monthly: float | None = None
    rent_growth_pct: float | None = None
    utilities_monthly: float | None = None
    utilities_growth_pct: float | None = None
    rm_monthly: float | None = None
    rm_growth_pct: float | None = None
    it_monthly: float | None = None
    it_growth_pct: float | None = None
    general_monthly: float | None = None
    general_growth_pct: float | None = None
    advertising_pct_revenue: float | None = None


class SiteBudgetAssumptionBulkUpdate(BaseModel):
    """Apply the same growth rates to all sites at once."""
    price_growth_pct: float | None = None
    pet_day_growth_pct: float | None = None
    wage_increase_pct: float | None = None


class SiteWeeklyBudgetRow(BaseModel):
    week_id: uuid.UUID
    week_label: str | None = None
    week_start: str | None = None
    week_end: str | None = None
    fy_month: int | None = None
    prior_year_pet_days_boarding: int | None = None
    prior_year_pet_days_daycare: int | None = None
    prior_year_pet_days_grooming: int | None = None
    prior_year_pet_days_wash: int | None = None
    prior_year_pet_days_training: int | None = None
    prior_year_revenue: float | None = None
    budget_pet_days_boarding: int | None = None
    budget_pet_days_daycare: int | None = None
    budget_pet_days_grooming: int | None = None
    budget_pet_days_wash: int | None = None
    budget_pet_days_training: int | None = None
    budget_revenue: float | None = None
    budget_labour: float | None = None
    budget_cogs: float | None = None
    budget_rent: float | None = None
    budget_utilities: float | None = None
    budget_rm: float | None = None
    budget_it: float | None = None
    budget_general: float | None = None
    budget_advertising: float | None = None
    is_overridden: bool = False
    override_revenue: float | None = None
    override_labour: float | None = None
    is_month_subtotal: bool = False


class SiteWeeklyOverridePayload(BaseModel):
    override_revenue: float | None = None
    override_labour: float | None = None
    is_overridden: bool = True


class SiteAnnualSummaryRow(BaseModel):
    location_id: uuid.UUID
    location_name: str
    state: str | None = None
    total_prior_pet_days: int = 0
    total_budget_pet_days: int = 0
    total_prior_revenue: float = 0.0
    total_budget_revenue: float = 0.0
    total_budget_labour: float = 0.0
    total_budget_costs: float = 0.0
    budget_contribution: float = 0.0
    assumptions_status: str = "default"
