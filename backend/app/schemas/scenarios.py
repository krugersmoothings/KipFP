import uuid
from datetime import datetime

from pydantic import BaseModel


class ScenarioCreate(BaseModel):
    name: str
    base_version_id: uuid.UUID
    description: str | None = None


class ScenarioRead(BaseModel):
    id: uuid.UUID
    name: str
    fy_year: int
    version_type: str
    status: str
    base_version_id: uuid.UUID | None = None
    description: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ScenarioAssumptionUpdate(BaseModel):
    entity_id: uuid.UUID | None = None
    assumption_key: str
    assumption_value: dict


class ScenarioMetric(BaseModel):
    scenario_id: uuid.UUID
    scenario_name: str
    revenue: float = 0
    gm_pct: float | None = None
    ebitda: float = 0
    ebitda_pct: float | None = None
    npat: float = 0
    operating_cf: float = 0
    closing_cash: float = 0
    total_debt: float = 0


class ScenarioCompareResponse(BaseModel):
    fy_year: int
    scenarios: list[ScenarioMetric]
