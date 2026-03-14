import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SyncRequest(BaseModel):
    fy_year: int = Field(..., ge=2020, le=2035)
    fy_month: int = Field(..., ge=1, le=12)


class SyncTriggerResponse(BaseModel):
    sync_run_id: uuid.UUID
    status: str = "queued"


class SyncRunRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID | None = None
    entity_code: str | None = None
    entity_name: str | None = None
    source_system: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: str | None = None
    records_upserted: int = 0
    error_detail: str | None = None
    triggered_by: str = "manual"

    model_config = {"from_attributes": True}
