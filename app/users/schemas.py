import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UserCreateRequest(BaseModel):
    email: EmailStr
    username: str = Field(min_length=3, max_length=150)
    password: str = Field(min_length=8)


class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(default=None, min_length=3, max_length=150)


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
