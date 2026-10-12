import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


# Postgres rejects NUL bytes in text columns, so control characters are refused here
USERNAME_PATTERN = r"^[^\x00-\x1f\x7f]+$"


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=150, pattern=USERNAME_PATTERN)
    password: str = Field(min_length=8)


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(
        default=None, min_length=3, max_length=150, pattern=USERNAME_PATTERN
    )


class DisableUserRequest(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


class UserReadResponse(ORMModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    is_active: bool
    created_at: datetime


class UserListItemResponse(ORMModel):
    id: uuid.UUID
    email: EmailStr
    username: str
    is_active: bool
