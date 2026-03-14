import uuid
from datetime import datetime

from pydantic import BaseModel


class VarianceRow(BaseModel):
    account_id: uuid.UUID | None = None
    account_code: str
    label: str
    is_subtotal: bool = False
    is_section_header: bool = False
    indent_level: int = 0
    actual: float = 0
    budget: float = 0
    variance_abs: float = 0
    variance_pct: float | None = None
    is_favourable: bool | None = None
    prior_year_actual: float = 0
    vs_pcp_abs: float = 0
    vs_pcp_pct: float | None = None
    commentary: str | None = None


class VarianceReportResponse(BaseModel):
    fy_year: int
    period_label: str
    version_id: uuid.UUID
    view_mode: str
    rows: list[VarianceRow]


class CommentaryPayload(BaseModel):
    version_id: uuid.UUID
    account_id: uuid.UUID
    period_id: uuid.UUID | None = None
    comment: str


class CommentaryRead(BaseModel):
    id: uuid.UUID
    version_id: uuid.UUID
    account_id: uuid.UUID
    period_id: uuid.UUID | None = None
    comment: str | None = None
    updated_by: uuid.UUID | None = None
    updated_at: datetime

    model_config = {"from_attributes": True}


class ExportRequest(BaseModel):
    type: str  # 'variance' | 'budget' | 'actuals'
    version_id: uuid.UUID | None = None
    fy_year: int
    format: str = "xlsx"  # 'xlsx' | 'pdf'
