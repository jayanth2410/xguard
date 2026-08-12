"""Audit Service - Comprehensive audit trail"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.models.database import AuditLog, WorkPackage

logger = structlog.get_logger()


class AuditService:
    """Service for audit logging and compliance"""

    def __init__(self, db: Session):
        self.db = db

    async def log_action(
        self,
        action: str,
        work_package_id: Optional[UUID] = None,
        actor_id: Optional[UUID] = None,
        actor_type: str = "user",
        old_value: Optional[Dict[str, Any]] = None,
        new_value: Optional[Dict[str, Any]] = None,
        details: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> AuditLog:
        """Create an audit log entry"""
        audit_log = AuditLog(
            action=action,
            work_package_id=work_package_id,
            actor_id=actor_id,
            actor_type=actor_type,
            old_value=old_value,
            new_value=new_value,
            details=details,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit_log)
        self.db.commit()
        self.db.refresh(audit_log)

        logger.info(
            "audit_log_created",
            action=action,
            work_package_id=str(work_package_id) if work_package_id else None,
            actor_id=str(actor_id) if actor_id else None,
        )

        return audit_log

    async def log_status_change(
        self,
        work_package_id: UUID,
        old_status: str,
        new_status: str,
        actor_id: Optional[UUID] = None,
        actor_type: str = "system",
    ) -> AuditLog:
        """Log a work package status change"""
        return await self.log_action(
            action="status_change",
            work_package_id=work_package_id,
            actor_id=actor_id,
            actor_type=actor_type,
            old_value={"status": old_status},
            new_value={"status": new_status},
        )

    async def log_review(
        self,
        work_package_id: UUID,
        reviewer_id: UUID,
        decision: str,
        comments: Optional[str] = None,
    ) -> AuditLog:
        """Log a review action"""
        return await self.log_action(
            action="review_submitted",
            work_package_id=work_package_id,
            actor_id=reviewer_id,
            actor_type="user",
            new_value={"decision": decision, "comments": comments},
        )

    async def log_execution(
        self,
        work_package_id: UUID,
        execution_id: UUID,
        status: str,
        executor_id: Optional[UUID] = None,
        details: Optional[str] = None,
    ) -> AuditLog:
        """Log an execution event"""
        return await self.log_action(
            action=f"execution_{status}",
            work_package_id=work_package_id,
            actor_id=executor_id,
            actor_type="system",
            new_value={"execution_id": str(execution_id), "status": status},
            details=details,
        )

    async def get_audit_logs(
        self,
        work_package_id: Optional[UUID] = None,
        actor_id: Optional[UUID] = None,
        action: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[AuditLog]:
        """Query audit logs with filters"""
        query = self.db.query(AuditLog)

        if work_package_id:
            query = query.filter(AuditLog.work_package_id == work_package_id)
        if actor_id:
            query = query.filter(AuditLog.actor_id == actor_id)
        if action:
            query = query.filter(AuditLog.action == action)
        if start_date:
            query = query.filter(AuditLog.created_at >= start_date)
        if end_date:
            query = query.filter(AuditLog.created_at <= end_date)

        return query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

    async def get_work_package_timeline(
        self,
        work_package_id: UUID,
    ) -> List[Dict[str, Any]]:
        """Get complete timeline of a work package"""
        logs = await self.get_audit_logs(work_package_id=work_package_id, limit=1000)

        timeline = []
        for log in reversed(logs):  # Chronological order
            timeline.append({
                "timestamp": log.created_at.isoformat(),
                "action": log.action,
                "actor_type": log.actor_type,
                "actor_id": str(log.actor_id) if log.actor_id else None,
                "details": log.details,
                "old_value": log.old_value,
                "new_value": log.new_value,
            })

        return timeline

    async def generate_compliance_report(
        self,
        work_package_id: UUID,
    ) -> Dict[str, Any]:
        """Generate a compliance report for a work package"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            return {"error": "Work package not found"}

        logs = await self.get_audit_logs(work_package_id=work_package_id, limit=1000)
        timeline = await self.get_work_package_timeline(work_package_id)

        # Extract key events
        creation_log = next((l for l in logs if l.action == "work_package_created"), None)
        review_logs = [l for l in logs if "review" in l.action]
        execution_logs = [l for l in logs if "execution" in l.action]

        return {
            "work_package_id": str(work_package_id),
            "ticket_id": work_package.ticket_id,
            "title": work_package.title,
            "change_type": work_package.change_type.value,
            "current_status": work_package.status.value,
            "risk_level": work_package.risk_level.value if work_package.risk_level else None,
            "execution_mode": work_package.execution_mode.value,
            "created_at": work_package.created_at.isoformat(),
            "maker_id": str(work_package.maker_id) if work_package.maker_id else None,
            "compliance_checks": {
                "has_review": len(review_logs) > 0,
                "review_count": len(review_logs),
                "has_execution_record": len(execution_logs) > 0,
                "has_rollback_plan": bool(work_package.rollback_procedure),
            },
            "timeline_summary": {
                "total_events": len(timeline),
                "first_event": timeline[0] if timeline else None,
                "last_event": timeline[-1] if timeline else None,
            },
            "full_timeline": timeline,
            "generated_at": datetime.utcnow().isoformat(),
        }
