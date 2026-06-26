"""Schemas for users and authentication"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, EmailStr


class UserCreate(BaseModel):
    """Schema for creating a user"""
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None
    role: str = "maker"  # maker, checker, executor, admin
    department: Optional[str] = None


class UserResponse(BaseModel):
    """Schema for user response"""
    id: UUID
    email: str
    username: str
    full_name: Optional[str]
    role: str
    department: Optional[str]
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class UserLogin(BaseModel):
    """Schema for user login"""
    username: str
    password: str


class Token(BaseModel):
    """Schema for JWT token response"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
