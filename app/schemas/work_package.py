"""Schemas for work packages"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from uuid import UUID
from pydantic import BaseModel, Field

from app.models.enums import (
    ChangeType, WorkflowStatus, ExecutionMode,
    RiskLevel, TriggerSource
)


class WorkPackageCreate(BaseModel):
    """Schema for creating a work package"""
    ticket_id: str = Field(..., description="ServiceNow ticket ID")
    title: str = Field(..., max_length=500)
    description: Optional[str] = None

    change_type: ChangeType
    trigger_source: TriggerSource = TriggerSource.MANUAL
    execution_mode: ExecutionMode = ExecutionMode.MANUAL

    # Optional AI-generated content
    generated_code: Optional[str] = None
    generated_procedure: Optional[str] = None
    impact_analysis: Optional[Dict[str, Any]] = None
    rollback_procedure: Optional[str] = None
    pre_checks: Optional[Dict[str, Any]] = None
    post_checks: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    ai_questions: Optional[List[Dict[str, Any]]] = None
    ai_question_responses: Optional[List[Dict[str, Any]]] = None

    # Target information
    target_infrastructure: Optional[List[str]] = None
    target_hosts: Optional[List[str]] = None

    # Scheduling
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    maintenance_window: Optional[str] = None



class WorkPackageUpdate(BaseModel):
    """Schema for updating a work package"""
    title: Optional[str] = None
    description: Optional[str] = None
    change_type: Optional[ChangeType] = None
    execution_mode: Optional[ExecutionMode] = None
    risk_level: Optional[RiskLevel] = None
    generated_code: Optional[str] = None
    generated_procedure: Optional[str] = None
    impact_analysis: Optional[Dict[str, Any]] = None
    rollback_procedure: Optional[str] = None
    pre_checks: Optional[Dict[str, Any]] = None
    post_checks: Optional[Dict[str, Any]] = None
    variables: Optional[Dict[str, Any]] = None
    ai_questions: Optional[List[Dict[str, Any]]] = None
    ai_question_responses: Optional[List[Dict[str, Any]]] = None
    target_infrastructure: Optional[List[str]] = None
    target_hosts: Optional[List[str]] = None
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    maintenance_window: Optional[str] = None


class WorkPackageResponse(BaseModel):
    """Schema for work package response"""
    id: UUID
    ticket_id: str
    title: str
    description: Optional[str]

    change_type: ChangeType
    trigger_source: TriggerSource
    execution_mode: ExecutionMode
    risk_level: RiskLevel
    status: WorkflowStatus

    generated_code: Optional[str]
    generated_procedure: Optional[str]
    impact_analysis: Optional[Dict[str, Any]]
    rollback_procedure: Optional[str]
    pre_checks: Optional[Dict[str, Any]]
    post_checks: Optional[Dict[str, Any]]
    variables: Optional[Dict[str, Any]]
    ai_questions: Optional[List[Dict[str, Any]]] = None
    ai_question_responses: Optional[List[Dict[str, Any]]] = None
    tokens_used: int = 0

    target_infrastructure: Optional[List[str]]
    target_hosts: Optional[List[str]]

    scheduled_start: Optional[datetime]
    scheduled_end: Optional[datetime]
    maintenance_window: Optional[str]

    maker_id: Optional[UUID]
    assigned_checker_id: Optional[UUID]

    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkPackageListResponse(BaseModel):
    """Schema for paginated work package list"""
    items: List[WorkPackageResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
