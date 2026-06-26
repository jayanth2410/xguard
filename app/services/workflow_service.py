"""Workflow Service - Orchestrates the Maker-Checker workflow"""
from typing import Optional, Dict, Any
from uuid import UUID
from sqlalchemy.orm import Session
import structlog

from app.models.database import WorkPackage
from app.models.enums import WorkflowStatus
from app.services.maker_service import MakerService
from app.services.checker_service import CheckerService
from app.services.validation_service import ValidationService
from app.services.execution_service import ExecutionService
from app.services.audit_service import AuditService

logger = structlog.get_logger()


class WorkflowService:
    """Orchestrates the complete Maker-Checker workflow"""

    def __init__(self, db: Session):
        self.db = db
        self.maker_service = MakerService(db)
        self.checker_service = CheckerService(db)
        self.validation_service = ValidationService(db)
        self.execution_service = ExecutionService(db)
        self.audit_service = AuditService(db)

    async def get_workflow_status(
        self,
        work_package_id: UUID,
    ) -> Dict[str, Any]:
        """Get complete workflow status for a work package"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            return {"error": "Work package not found"}

        # Determine current phase
        phase = self._get_current_phase(work_package.status)

        # Get phase-specific details
        details = {}

        if phase in ["review", "review_complete"]:
            reviews = await self.checker_service.get_reviews_for_work_package(work_package_id)
            details["reviews"] = [
                {
                    "reviewer_id": str(r.reviewer_id),
                    "decision": r.decision,
                    "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                }
                for r in reviews
            ]

        if phase in ["validation", "validation_complete"]:
            session = await self.validation_service.get_session_for_work_package(work_package_id)
            if session:
                details["validation"] = await self.validation_service.get_session_status(session.id)

        if phase in ["execution", "execution_complete", "completed"]:
            executions = await self.execution_service.get_executions_for_work_package(work_package_id)
            details["executions"] = [
                await self.execution_service.get_execution_status(e.id)
                for e in executions
            ]

        return {
            "work_package_id": str(work_package_id),
            "ticket_id": work_package.ticket_id,
            "title": work_package.title,
            "status": work_package.status.value,
            "phase": phase,
            "change_type": work_package.change_type.value,
            "execution_mode": work_package.execution_mode.value,
            "risk_level": work_package.risk_level.value if work_package.risk_level else None,
            "next_actions": self._get_next_actions(work_package.status),
            "can_proceed": self._can_proceed(work_package.status),
            "details": details,
        }

    def _get_current_phase(self, status: WorkflowStatus) -> str:
        """Map status to workflow phase"""
        phase_mapping = {
            WorkflowStatus.DRAFT: "creation",
            WorkflowStatus.PENDING_REVIEW: "review",
            WorkflowStatus.IN_REVIEW: "review",
            WorkflowStatus.APPROVED: "review_complete",
            WorkflowStatus.REJECTED: "review_complete",
            WorkflowStatus.REWORK_REQUIRED: "creation",
            WorkflowStatus.PENDING_VALIDATION: "validation",
            WorkflowStatus.VALIDATION_IN_PROGRESS: "validation",
            WorkflowStatus.VALIDATED: "validation_complete",
            WorkflowStatus.VALIDATION_FAILED: "validation",
            WorkflowStatus.PENDING_EXECUTION: "execution",
            WorkflowStatus.EXECUTING: "execution",
            WorkflowStatus.EXECUTED: "execution_complete",
            WorkflowStatus.EXECUTION_FAILED: "execution",
            WorkflowStatus.ROLLED_BACK: "execution_complete",
            WorkflowStatus.COMPLETED: "completed",
        }
        return phase_mapping.get(status, "unknown")

    def _get_next_actions(self, status: WorkflowStatus) -> list:
        """Get available next actions for a status"""
        actions_mapping = {
            WorkflowStatus.DRAFT: ["edit", "submit_for_review"],
            WorkflowStatus.PENDING_REVIEW: ["start_review"],
            WorkflowStatus.IN_REVIEW: ["approve", "reject", "request_rework"],
            WorkflowStatus.APPROVED: ["start_validation"],
            WorkflowStatus.REJECTED: [],
            WorkflowStatus.REWORK_REQUIRED: ["edit", "submit_for_review"],
            WorkflowStatus.PENDING_VALIDATION: [],
            WorkflowStatus.VALIDATION_IN_PROGRESS: ["submit_response", "fail_validation"],
            WorkflowStatus.VALIDATED: ["start_execution"],
            WorkflowStatus.VALIDATION_FAILED: ["restart_validation"],
            WorkflowStatus.PENDING_EXECUTION: [],
            WorkflowStatus.EXECUTING: [],
            WorkflowStatus.EXECUTED: ["complete"],
            WorkflowStatus.EXECUTION_FAILED: ["retry_execution", "restart_workflow"],
            WorkflowStatus.ROLLED_BACK: ["retry_execution", "close"],
            WorkflowStatus.COMPLETED: [],
        }
        return actions_mapping.get(status, [])

    def _can_proceed(self, status: WorkflowStatus) -> bool:
        """Check if workflow can proceed to next phase"""
        proceed_statuses = {
            WorkflowStatus.DRAFT,
            WorkflowStatus.PENDING_REVIEW,
            WorkflowStatus.IN_REVIEW,
            WorkflowStatus.APPROVED,
            WorkflowStatus.REWORK_REQUIRED,
            WorkflowStatus.VALIDATION_IN_PROGRESS,
            WorkflowStatus.VALIDATED,
            WorkflowStatus.EXECUTED,
        }
        return status in proceed_statuses

    async def transition_to_validation(
        self,
        work_package_id: UUID,
    ) -> Dict[str, Any]:
        """Transition approved work package to validation phase"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status != WorkflowStatus.APPROVED:
            raise ValueError(f"Cannot start validation from status: {work_package.status}")

        # Create validation session
        session = await self.validation_service.create_validation_session(work_package_id)

        # Log the transition
        await self.audit_service.log_status_change(
            work_package_id=work_package_id,
            old_status=WorkflowStatus.APPROVED.value,
            new_status=WorkflowStatus.VALIDATION_IN_PROGRESS.value,
            actor_type="system",
        )

        return {
            "work_package_id": str(work_package_id),
            "validation_session_id": str(session.id),
            "status": "validation_started",
            "questions": await self.validation_service.get_session_status(session.id),
        }

    async def transition_to_execution(
        self,
        work_package_id: UUID,
        executor_id: Optional[UUID] = None,
    ) -> Dict[str, Any]:
        """Transition validated work package to execution phase"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status != WorkflowStatus.VALIDATED:
            raise ValueError(f"Cannot start execution from status: {work_package.status}")

        from app.schemas.execution import ExecutionRequest

        # Start execution
        execution = await self.execution_service.start_execution(
            ExecutionRequest(work_package_id=work_package_id),
            executor_id=executor_id,
        )

        # Log the transition
        await self.audit_service.log_status_change(
            work_package_id=work_package_id,
            old_status=WorkflowStatus.VALIDATED.value,
            new_status=WorkflowStatus.PENDING_EXECUTION.value,
            actor_id=executor_id,
            actor_type="user" if executor_id else "system",
        )

        return {
            "work_package_id": str(work_package_id),
            "execution_id": str(execution.id),
            "status": "execution_started",
            "execution_details": await self.execution_service.get_execution_status(execution.id),
        }

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get summary statistics for dashboard"""
        from sqlalchemy import func

        status_counts = (
            self.db.query(WorkPackage.status, func.count(WorkPackage.id))
            .group_by(WorkPackage.status)
            .all()
        )

        counts = {status.value: count for status, count in status_counts}

        return {
            "total_work_packages": sum(counts.values()),
            "by_status": counts,
            "pending_review": counts.get(WorkflowStatus.PENDING_REVIEW.value, 0),
            "in_review": counts.get(WorkflowStatus.IN_REVIEW.value, 0),
            "pending_validation": counts.get(WorkflowStatus.VALIDATION_IN_PROGRESS.value, 0),
            "pending_execution": counts.get(WorkflowStatus.PENDING_EXECUTION.value, 0),
            "completed": counts.get(WorkflowStatus.COMPLETED.value, 0),
            "failed": (
                counts.get(WorkflowStatus.EXECUTION_FAILED.value, 0) +
                counts.get(WorkflowStatus.VALIDATION_FAILED.value, 0) +
                counts.get(WorkflowStatus.REJECTED.value, 0)
            ),
        }
