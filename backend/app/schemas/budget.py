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


# ── Calculation trigger / status ──────────────────────────────────────────────


class CalculationTriggerResponse(BaseModel):
    task_id: str
    status: str = "queued"


class CalculationStatusResponse(BaseModel):
    task_id: str | None = None
    status: str
    result: dict | None = None


# ── Model output (reuses FinancialRow / FinancialStatementResponse) ───────────

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
