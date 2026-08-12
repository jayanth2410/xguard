"""Execution completion rules."""
from datetime import datetime
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from app.models.database import ExecutionRecord, WorkPackage
from app.models.enums import WorkflowStatus

logger = structlog.get_logger()


class ExecutionService:
    """Finalize a work package after its recorded commands succeed."""

    def __init__(self, db: Session):
        self.db = db

    async def complete_execution(self, work_package_id: UUID) -> WorkPackage:
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()
        if not work_package:
            raise ValueError("Work package not found")

        allowed_statuses = {WorkflowStatus.EXECUTED, WorkflowStatus.EXECUTING}
        if work_package.status not in allowed_statuses:
            status_messages = {
                WorkflowStatus.APPROVED: "Execution has not started yet. Run the approved implementation successfully before marking this work package as complete.",
                WorkflowStatus.PENDING_EXECUTION: "Execution has not started yet. Run the approved implementation successfully before marking this work package as complete.",
                WorkflowStatus.EXECUTION_FAILED: "Execution failed, so this work package cannot be marked as complete. Resolve the failure or complete the rollback process.",
                WorkflowStatus.ROLLED_BACK: "The change was rolled back and was not implemented. Close it as rolled back or retry the execution instead of marking it as complete.",
                WorkflowStatus.COMPLETED: "This work package is already completed.",
            }
            raise ValueError(status_messages.get(
                work_package.status,
                "This work package is not ready to be completed. Finish the required workflow steps and successful execution first.",
            ))

        execution = self.db.query(ExecutionRecord).filter(
            ExecutionRecord.work_package_id == work_package_id
        ).order_by(ExecutionRecord.started_at.desc()).first()
        if not execution or not execution.command_log:
            raise ValueError("Cannot complete before at least one command has executed")
        if any(not entry.get("success", False) for entry in execution.command_log):
            raise ValueError(
                "Cannot complete because the execution contains failed commands. "
                "Resolve the failure or complete rollback first."
            )

        work_package.status = WorkflowStatus.COMPLETED
        execution.status = "success"
        execution.completed_at = datetime.utcnow()
        if execution.started_at:
            execution.duration_seconds = (
                execution.completed_at - execution.started_at
            ).total_seconds()
        self.db.commit()
        self.db.refresh(work_package)
        logger.info("work_package_completed", work_package_id=str(work_package_id))
        return work_package
