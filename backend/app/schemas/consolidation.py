import uuid
from datetime import datetime
from decimal import Decimal

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
