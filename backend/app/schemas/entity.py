import uuid
from datetime import date

from pydantic import BaseModel


class EntityRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str | None = None
    source_system: str | None = None
    is_active: bool = True
    currency: str = "AUD"
    consolidation_method: str = "full"
    acquisition_date: date | None = None

    model_config = {"from_attributes": True}


class LocationRead(BaseModel):
    id: uuid.UUID
    code: str | None = None
    name: str | None = None
    entity_id: uuid.UUID | None = None
    state: str | None = None
    capacity_dogs: int | None = None
    is_active: bool = True

    model_config = {"from_attributes": True}
