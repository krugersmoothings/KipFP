import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr

from app.db.models.user import UserRole


class UserRead(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    role: UserRole = UserRole.viewer
