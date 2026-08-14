"""Build a work-package audit from authoritative workflow records."""
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.database import ExecutionRecord, Review, WorkPackage


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _user_summary(user) -> Optional[Dict[str, Any]]:
    if not user:
        return None
    return {
        "id": str(user.id),
        "username": user.username,
        "full_name": user.full_name or user.username,
        "role": user.role,
    }


class AuditService:
    """Read review and execution history without maintaining a duplicate log table."""

    def __init__(self, db: Session):
        self.db = db

    def _get_work_package(self, work_package_id: UUID) -> Optional[WorkPackage]:
        return self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

    async def get_audit_report(self, work_package_id: UUID) -> Dict[str, Any]:
        work_package = self._get_work_package(work_package_id)
        if not work_package:
            return {"error": "Work package not found"}

        reviews = self.db.query(Review).filter(
            Review.work_package_id == work_package_id
        ).order_by(Review.started_at.asc()).all()
        executions = self.db.query(ExecutionRecord).filter(
            ExecutionRecord.work_package_id == work_package_id
        ).order_by(ExecutionRecord.started_at.asc()).all()

        review_items = [self._serialize_review(review) for review in reviews]
        execution_items = [
            self._serialize_execution(execution) for execution in executions
        ]
        timeline = self._build_timeline(work_package, reviews, executions)
        command_count = sum(
            len(execution.command_log or []) for execution in executions
        )
        failed_commands = sum(
            1
            for execution in executions
            for command in (execution.command_log or [])
            if not command.get("success", False)
        )
        rollback_commands = sum(
            1
            for execution in executions
            for command in (execution.command_log or [])
            if command.get("is_rollback", False)
        )

        return {
            "work_package": {
                "id": str(work_package.id),
                "ticket_id": work_package.ticket_id,
                "title": work_package.title,
                "description": work_package.description,
                "change_type": _enum_value(work_package.change_type),
                "status": _enum_value(work_package.status),
                "risk_level": _enum_value(work_package.risk_level),
                "execution_mode": _enum_value(work_package.execution_mode),
                "target_hosts": work_package.target_hosts or [],
                "maker": _user_summary(work_package.maker),
                "created_at": _iso(work_package.created_at),
                "updated_at": _iso(work_package.updated_at),
            },
            "summary": {
                "review_count": len(reviews),
                "execution_count": len(executions),
                "command_count": command_count,
                "failed_commands": failed_commands,
                "rollback_commands": rollback_commands,
                "has_approved_review": any(
                    review.decision == "approved" for review in reviews
                ),
                "has_rollback_plan": bool(work_package.rollback_procedure),
            },
            "reviews": review_items,
            "executions": execution_items,
            "timeline": timeline,
            "generated_at": datetime.utcnow().isoformat(),
        }

    @staticmethod
    def _serialize_review(review: Review) -> Dict[str, Any]:
        return {
            "id": str(review.id),
            "decision": review.decision,
            "reviewer": _user_summary(review.reviewer),
            "comments": review.comments,
            "implementation_notes": review.code_review_notes,
            "rollback_notes": review.rollback_review_notes,
            "security_notes": review.security_review_notes,
            "impact_notes": review.impact_review_notes,
            "approved_execution_mode": _enum_value(
                review.approved_execution_mode
            ),
            "started_at": _iso(review.started_at),
            "completed_at": _iso(review.completed_at),
        }

    @staticmethod
    def _serialize_execution(execution: ExecutionRecord) -> Dict[str, Any]:
        commands = []
        for index, command in enumerate(execution.command_log or [], start=1):
            commands.append({
                "sequence": index,
                "command": command.get("command", ""),
                "host": command.get("host", ""),
                "timestamp": command.get("timestamp"),
                "success": bool(command.get("success", False)),
                "exit_code": command.get("exit_code"),
                "output": command.get("output", ""),
                "stderr": command.get("stderr", ""),
                "is_rollback": bool(command.get("is_rollback", False)),
            })
        return {
            "id": str(execution.id),
            "status": execution.status,
            "execution_mode": _enum_value(execution.execution_mode),
            "executor": _user_summary(execution.executor),
            "started_at": _iso(execution.started_at),
            "completed_at": _iso(execution.completed_at),
            "duration_seconds": execution.duration_seconds,
            "exit_code": execution.exit_code,
            "rollback_initiated": bool(execution.rollback_initiated),
            "rollback_status": execution.rollback_status,
            "output_log": execution.output_log,
            "error_log": execution.error_log,
            "rollback_log": execution.rollback_log,
            "commands": commands,
        }

    @staticmethod
    def _build_timeline(
        work_package: WorkPackage,
        reviews: List[Review],
        executions: List[ExecutionRecord],
    ) -> List[Dict[str, Any]]:
        events = [{
            "timestamp": _iso(work_package.created_at),
            "category": "package",
            "action": "work_package_created",
            "title": "Work package created",
            "actor": _user_summary(work_package.maker),
            "status": "draft",
            "details": {"ticket_id": work_package.ticket_id},
        }]

        for review in reviews:
            events.append({
                "timestamp": _iso(review.started_at),
                "category": "review",
                "action": "review_started",
                "title": "Review started",
                "actor": _user_summary(review.reviewer),
                "status": "in_progress",
                "details": {},
            })
            if review.completed_at:
                events.append({
                    "timestamp": _iso(review.completed_at),
                    "category": "review",
                    "action": f"review_{review.decision}",
                    "title": f"Review {review.decision.replace('_', ' ')}",
                    "actor": _user_summary(review.reviewer),
                    "status": review.decision,
                    "details": {
                        "comments": review.comments,
                        "implementation_notes": review.code_review_notes,
                        "rollback_notes": review.rollback_review_notes,
                    },
                })

        for execution in executions:
            events.append({
                "timestamp": _iso(execution.started_at),
                "category": "execution",
                "action": "execution_started",
                "title": "Execution session started",
                "actor": _user_summary(execution.executor),
                "status": execution.status,
                "details": {"execution_id": str(execution.id)},
            })
            for index, command in enumerate(execution.command_log or [], start=1):
                is_rollback = bool(command.get("is_rollback", False))
                success = bool(command.get("success", False))
                events.append({
                    "timestamp": command.get("timestamp") or _iso(execution.started_at),
                    "category": "rollback" if is_rollback else "execution",
                    "action": "rollback_command" if is_rollback else "execution_command",
                    "title": (
                        f"Rollback command {index}"
                        if is_rollback else f"Implementation command {index}"
                    ),
                    "actor": _user_summary(execution.executor),
                    "status": "success" if success else "failed",
                    "details": {
                        "host": command.get("host"),
                        "command": command.get("command"),
                        "exit_code": command.get("exit_code"),
                        "output": command.get("output"),
                        "stderr": command.get("stderr"),
                    },
                })
            if execution.completed_at:
                events.append({
                    "timestamp": _iso(execution.completed_at),
                    "category": "rollback" if execution.rollback_initiated else "execution",
                    "action": "execution_finished",
                    "title": "Execution session finished",
                    "actor": _user_summary(execution.executor),
                    "status": execution.status,
                    "details": {
                        "duration_seconds": execution.duration_seconds,
                        "rollback_status": execution.rollback_status,
                    },
                })

        return sorted(events, key=lambda event: event.get("timestamp") or "")

    async def get_work_package_timeline(
        self,
        work_package_id: UUID,
    ) -> List[Dict[str, Any]]:
        report = await self.get_audit_report(work_package_id)
        return report.get("timeline", [])

    async def generate_compliance_report(
        self,
        work_package_id: UUID,
    ) -> Dict[str, Any]:
        report = await self.get_audit_report(work_package_id)
        if "error" in report:
            return report
        summary = report["summary"]
        return {
            **report,
            "compliance_checks": {
                "has_review": summary["review_count"] > 0,
                "has_execution_record": summary["execution_count"] > 0,
                "has_rollback_plan": summary["has_rollback_plan"],
                "has_approved_review": summary["has_approved_review"],
            },
        }
