"""Schemas for execution"""
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import UUID
from pydantic import BaseModel

from app.models.enums import ExecutionMode


class ExecutionRequest(BaseModel):
    """Schema for requesting execution"""
    work_package_id: UUID
    execution_mode: Optional[ExecutionMode] = None
    dry_run: bool = False


class ExecutionStatus(BaseModel):
    """Schema for execution status"""
    status: str
    jit_verification_passed: Optional[bool]
    jit_verification_details: Optional[Dict[str, Any]]
    output_log: Optional[str]
    error_log: Optional[str]
    exit_code: Optional[int]
    rollback_initiated: bool
    rollback_status: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]


class ExecutionResponse(BaseModel):
    """Schema for execution response"""
    id: UUID
    work_package_id: UUID
    executor_id: Optional[UUID]
    execution_mode: ExecutionMode
    status: str
    jit_verification_passed: Optional[bool]
    jit_verification_details: Optional[Dict[str, Any]]
    output_log: Optional[str]
    error_log: Optional[str]
    exit_code: Optional[int]
    rollback_initiated: bool
    rollback_status: Optional[str]
    rollback_log: Optional[str]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    duration_seconds: Optional[float]

    class Config:
        from_attributes = True
