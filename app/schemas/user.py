"""User and authentication API schemas."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=100)
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    full_name: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=50)
    department: str | None = Field(default=None, max_length=100)
    is_active: bool = True


class SeedUsersRequest(BaseModel):
    users: list[UserCreate] = Field(min_length=1, max_length=5)


class UserResponse(BaseModel):
    id: UUID
    email: str
    username: str
    full_name: str | None
    role: str
    department: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class SeedUsersResponse(BaseModel):
    message: str
    users: list[UserResponse]
