"""Schemas for validation sessions"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel

from app.models.enums import ValidationQuestionType


class ValidationQuestionResponse(BaseModel):
    """Schema for validation question"""
    id: UUID
    question_key: str
    question_text: str
    question_type: ValidationQuestionType
    category: Optional[str]
    is_required: bool
    options: Optional[List[str]]
    order: int

    class Config:
        from_attributes = True


class ValidationResponseCreate(BaseModel):
    """Schema for submitting a validation response"""
    question_id: UUID
    response_text: Optional[str] = None
    response_data: Optional[Dict[str, Any]] = None


class ValidationResponseModel(BaseModel):
    """Schema for validation response"""
    id: UUID
    question_id: UUID
    response_text: Optional[str]
    response_data: Optional[Dict[str, Any]]
    responded_by: Optional[UUID]
    responded_at: datetime

    class Config:
        from_attributes = True


class ValidationSessionCreate(BaseModel):
    """Schema for creating a validation session"""
    work_package_id: UUID


class ValidationSessionResponse(BaseModel):
    """Schema for validation session response"""
    id: UUID
    work_package_id: UUID
    status: str
    all_questions_answered: bool
    started_at: datetime
    completed_at: Optional[datetime]
    questions: List[ValidationQuestionResponse] = []
    responses: List[ValidationResponseModel] = []

    # Computed fields
    total_questions: int = 0
    answered_questions: int = 0
    unanswered_questions: List[ValidationQuestionResponse] = []

    class Config:
        from_attributes = True


class ValidationQuestionsConfig(BaseModel):
    """Configuration for dynamic validation questions"""
    change_type: str
    questions: List[Dict[str, Any]]
