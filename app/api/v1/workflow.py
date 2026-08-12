"""Workflow API endpoints"""
from uuid import UUID
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.workflow_service import WorkflowService
from app.services.audit_service import AuditService

router = APIRouter()


@router.get("/dashboard")
async def get_dashboard(
    db: Session = Depends(get_db),
):
    """Get dashboard summary"""
    service = WorkflowService(db)
    summary = await service.get_dashboard_summary()
    return summary


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
