import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


class BigQuerySyncRequest(BaseModel):
    date_from: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")
    date_to: str = Field(..., pattern=r"^\d{4}-\d{2}-\d{2}$")


class PetDayActual(BaseModel):
    date: date
    service_type: str
    pet_days: int
    revenue_aud: float | None = None

    model_config = {"from_attributes": True}


class PetDayWeekly(BaseModel):
    week_start: date
    week_end: date
    week_label: str | None = None
    boarding: int = 0
    daycare: int = 0
    grooming: int = 0
    wash: int = 0
    training: int = 0
    total_pet_days: int = 0
    total_revenue: float = 0.0


class PetDaySiteSummary(BaseModel):
    location_id: uuid.UUID
    location_name: str
    total_boarding: int = 0
    total_daycare: int = 0
    total_grooming: int = 0
    total_wash: int = 0
    total_training: int = 0
    total_pet_days: int = 0
    total_revenue: float = 0.0


class ForwardBookingWeek(BaseModel):
    property_name: str
    location_id: uuid.UUID | None = None
    location_name: str | None = None
    service_type: str
    week_start: date
    pet_days_booked: int = 0
    revenue_booked: float = 0.0


class PropertyMappingRead(BaseModel):
    id: uuid.UUID
    bigquery_property_id: int
    bigquery_property_name: str | None = None
    bigquery_url_slug: str | None = None
    location_id: uuid.UUID | None = None
    is_active: bool = True
    notes: str | None = None

    model_config = {"from_attributes": True}
