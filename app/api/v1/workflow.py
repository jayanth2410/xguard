"""Workflow API endpoints"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.workflow_service import WorkflowService
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("/status/{work_package_id}")
async def get_workflow_status(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get complete workflow status for a work package"""
    service = WorkflowService(db)
    status = await service.get_workflow_status(work_package_id)

    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    return status


@router.post("/{work_package_id}/start-validation")
async def start_validation(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Transition to validation phase"""
    service = WorkflowService(db)

    try:
        result = await service.transition_to_validation(work_package_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.post("/{work_package_id}/start-execution")
async def start_execution(
    work_package_id: UUID,
    executor_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """Transition to execution phase"""
    service = WorkflowService(db)

    try:
        result = await service.transition_to_execution(work_package_id, executor_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return result


@router.get("/dashboard")
async def get_dashboard(
    db: Session = Depends(get_db),
):
    """Get dashboard summary"""
    service = WorkflowService(db)
    summary = await service.get_dashboard_summary()
    return summary


@router.get("/audit/{work_package_id}")
async def get_audit_trail(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get audit trail for a work package"""
    service = AuditService(db)
    logs = await service.get_audit_logs(work_package_id=work_package_id)

    return {
        "work_package_id": str(work_package_id),
        "log_count": len(logs),
        "logs": [
            {
                "id": str(log.id),
                "action": log.action,
                "actor_type": log.actor_type,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "details": log.details,
                "created_at": log.created_at.isoformat(),
            }
            for log in logs
        ],
    }


@router.get("/audit/{work_package_id}/timeline")
async def get_timeline(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get complete timeline for a work package"""
    service = AuditService(db)
    timeline = await service.get_work_package_timeline(work_package_id)
    return {"timeline": timeline}


@router.get("/audit/{work_package_id}/compliance")
async def get_compliance_report(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Generate compliance report for a work package"""
    service = AuditService(db)
    report = await service.generate_compliance_report(work_package_id)

    if "error" in report:
        raise HTTPException(status_code=404, detail=report["error"])

    return report
