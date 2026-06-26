"""Schemas for reviews"""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel
from enum import Enum

from app.models.enums import ExecutionMode


class ReviewDecision(str, Enum):
    """Review decision options"""
    APPROVED = "approved"
    REJECTED = "rejected"
    REWORK_REQUIRED = "rework_required"


class ReviewCreate(BaseModel):
    """Schema for creating a review"""
    work_package_id: UUID
    decision: ReviewDecision
    comments: Optional[str] = None
    code_review_notes: Optional[str] = None
    security_review_notes: Optional[str] = None
    impact_review_notes: Optional[str] = None
    approved_execution_mode: Optional[ExecutionMode] = None


class ReviewResponse(BaseModel):
    """Schema for review response"""
    id: UUID
    work_package_id: UUID
    reviewer_id: UUID
    decision: str
    comments: Optional[str]
    code_review_notes: Optional[str]
    security_review_notes: Optional[str]
    impact_review_notes: Optional[str]
    approved_execution_mode: Optional[ExecutionMode]
    started_at: datetime
    completed_at: Optional[datetime]

    class Config:
        from_attributes = True
