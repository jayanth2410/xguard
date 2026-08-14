"""Work-package creation, editing, submission, and retrieval."""
from typing import List, Optional
from uuid import UUID

import structlog
from sqlalchemy.orm import Session

from app.models.database import WorkPackage
from app.models.enums import ChangeType, WorkflowStatus
from app.schemas.work_package import WorkPackageCreate, WorkPackageUpdate

logger = structlog.get_logger()


class MakerService:
    """Manage work packages owned by the maker workflow."""

    def __init__(self, db: Session):
        self.db = db

    async def create_work_package(
        self,
        data: WorkPackageCreate,
        maker_id: Optional[UUID] = None,
    ) -> WorkPackage:
        work_package = WorkPackage(
            ticket_id=data.ticket_id,
            title=data.title,
            description=data.description,
            change_type=data.change_type,
            trigger_source=data.trigger_source,
            execution_mode=data.execution_mode,
            status=WorkflowStatus.DRAFT,
            generated_code=data.generated_code,
            generated_procedure=data.generated_procedure,
            impact_analysis=data.impact_analysis,
            rollback_procedure=data.rollback_procedure,
            pre_checks=data.pre_checks,
            post_checks=data.post_checks,
            variables=data.variables,
            ai_questions=data.ai_questions or [],
            ai_question_responses=data.ai_question_responses or [],
            target_infrastructure=data.target_infrastructure,
            target_hosts=data.target_hosts,
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end,
            maintenance_window=data.maintenance_window,
            maker_id=maker_id,
        )
        self.db.add(work_package)
        self.db.commit()
        self.db.refresh(work_package)
        logger.info(
            "work_package_created",
            work_package_id=str(work_package.id),
            ticket_id=work_package.ticket_id,
            change_type=work_package.change_type.value,
        )
        return work_package

    async def update_work_package(
        self,
        work_package_id: UUID,
        data: WorkPackageUpdate,
    ) -> Optional[WorkPackage]:
        work_package = await self.get_work_package(work_package_id)
        if not work_package:
            return None
        if work_package.status not in {
            WorkflowStatus.DRAFT,
            WorkflowStatus.REWORK_REQUIRED,
        }:
            raise ValueError(
                f"Cannot update work package in status: {work_package.status.value}"
            )

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(work_package, field, value)

        self.db.commit()
        self.db.refresh(work_package)
        logger.info(
            "work_package_updated",
            work_package_id=str(work_package_id),
            updated_fields=list(update_data),
        )
        return work_package

    async def submit_for_review(self, work_package_id: UUID) -> WorkPackage:
        work_package = await self.get_work_package(work_package_id)
        if not work_package:
            raise ValueError("Work package not found")
        if work_package.status not in {
            WorkflowStatus.DRAFT,
            WorkflowStatus.REWORK_REQUIRED,
        }:
            raise ValueError(
                f"Cannot submit for review from status: {work_package.status.value}"
            )

        answers = {
            answer.get("question_key"): answer.get("response_text")
            for answer in (work_package.ai_question_responses or [])
            if answer.get("question_key")
            and str(answer.get("response_text", "")).strip()
        }
        unanswered = [
            question
            for question in (work_package.ai_questions or [])
            if question.get("is_required", True)
            and question.get("question_key") not in answers
        ]
        if unanswered:
            raise ValueError(
                "Answer all required clarification questions before review "
                f"({len(unanswered)} remaining)"
            )
        if not work_package.generated_code or not work_package.rollback_procedure:
            raise ValueError(
                "Generate the final implementation and rollback code before review"
            )

        work_package.status = WorkflowStatus.PENDING_REVIEW
        self.db.commit()
        self.db.refresh(work_package)
        logger.info(
            "work_package_submitted_for_review",
            work_package_id=str(work_package_id),
        )
        return work_package

    async def get_work_package(
        self,
        work_package_id: UUID,
    ) -> Optional[WorkPackage]:
        return self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

    async def list_work_packages(
        self,
        status: Optional[WorkflowStatus] = None,
        change_type: Optional[ChangeType] = None,
        ticket_id: Optional[str] = None,
        maker_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkPackage]:
        query = self.db.query(WorkPackage)
        if status:
            query = query.filter(WorkPackage.status == status)
        if change_type:
            query = query.filter(WorkPackage.change_type == change_type)
        if ticket_id:
            query = query.filter(
                WorkPackage.ticket_id.ilike(f"%{ticket_id.strip()}%")
            )
        if maker_id:
            query = query.filter(WorkPackage.maker_id == maker_id)

        return (
            query.order_by(WorkPackage.created_at.desc())
            .offset(skip)
            .limit(limit)
            .all()
        )
