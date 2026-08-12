"""Dashboard aggregation for the XGuard workflow."""
from datetime import datetime
from typing import Dict, Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.database import WorkPackage
from app.models.enums import WorkflowStatus


class WorkflowService:
    """Provide workflow-level dashboard statistics."""

    def __init__(self, db: Session):
        self.db = db

    async def get_dashboard_summary(self) -> Dict[str, Any]:
        status_counts = (
            self.db.query(WorkPackage.status, func.count(WorkPackage.id))
            .group_by(WorkPackage.status)
            .all()
        )
        counts = {status.value: count for status, count in status_counts}
        current_month = datetime.utcnow().strftime("%Y-%m")
        monthly_tokens = self.db.query(
            func.coalesce(func.sum(WorkPackage.monthly_tokens_used), 0)
        ).filter(WorkPackage.token_usage_month == current_month).scalar()

        return {
            "total_work_packages": sum(counts.values()),
            "by_status": counts,
            "draft": counts.get(WorkflowStatus.DRAFT.value, 0),
            "pending_review": counts.get(WorkflowStatus.PENDING_REVIEW.value, 0),
            "in_review": counts.get(WorkflowStatus.IN_REVIEW.value, 0),
            "ready_execution": counts.get(WorkflowStatus.APPROVED.value, 0),
            "pending_execution": counts.get(WorkflowStatus.PENDING_EXECUTION.value, 0),
            "completed": counts.get(WorkflowStatus.COMPLETED.value, 0),
            "failed": counts.get(WorkflowStatus.EXECUTION_FAILED.value, 0),
            "tokens_used_this_month": int(monthly_tokens or 0),
        }
