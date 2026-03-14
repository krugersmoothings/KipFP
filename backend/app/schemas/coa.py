import uuid
from datetime import date

from pydantic import BaseModel


class SourceAccountRead(BaseModel):
    entity_id: uuid.UUID
    entity_code: str
    entity_name: str | None = None
    source_account_code: str
    source_account_name: str | None = None
    is_mapped: bool = False
    mapping_id: uuid.UUID | None = None
    target_account_code: str | None = None
    target_account_name: str | None = None


class AccountMappingRead(BaseModel):
    id: uuid.UUID
    entity_id: uuid.UUID
    source_account_code: str
    source_account_name: str | None = None
    target_account_id: uuid.UUID
    target_account_code: str | None = None
    target_account_name: str | None = None
    multiplier: float = 1.0
    effective_from: date
    effective_to: date | None = None
    notes: str | None = None

    model_config = {"from_attributes": True}


class AccountMappingSave(BaseModel):
    entity_id: uuid.UUID
    source_account_code: str
    source_account_name: str | None = None
    target_account_id: uuid.UUID
    multiplier: float = 1.0
    effective_from: date
    notes: str | None = None


class TargetAccountRead(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    account_type: str | None = None
    statement: str | None = None

    model_config = {"from_attributes": True}


class ValidationResult(BaseModel):
    total_source_accounts: int
    mapped_count: int
    unmapped_count: int
    unmapped_accounts: list[SourceAccountRead]
