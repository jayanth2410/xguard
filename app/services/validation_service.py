"""Validation Service - Dynamic context-aware pre-execution validation"""
from typing import Optional, List, Dict, Any
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.models.database import (
    WorkPackage, ValidationSession, ValidationQuestion, ValidationResponse
)
from app.models.enums import WorkflowStatus, ChangeType, ValidationQuestionType
from app.core.validation_questions import get_questions_for_change_type
from app.schemas.validation import ValidationResponseCreate

logger = structlog.get_logger()


class ValidationService:
    """Service for dynamic execution validation with Q&A"""

    def __init__(self, db: Session):
        self.db = db

    async def _fetch_ci_info(self, ticket_id: str) -> Optional[Dict[str, Any]]:
        """Fetch CI (Configuration Item) info from ServiceNow"""
        try:
            from app.services.servicenow_service import servicenow

            # Try to get change request first
            if ticket_id.startswith('CHG'):
                record = await servicenow.get_change_request(ticket_id)
            elif ticket_id.startswith('INC'):
                record = await servicenow.get_incident(ticket_id)
            else:
                record = await servicenow.get_request(ticket_id)

            if record and record.get('cmdb_ci'):
                ci = record['cmdb_ci']
                if isinstance(ci, dict):
                    return {
                        'ci_name': ci.get('display_value', ''),
                        'ci_link': ci.get('link', ''),
                        'ci_sys_id': ci.get('value', ''),
                    }
                else:
                    return {'ci_name': str(ci)}

            return None
        except Exception as e:
            logger.warning("failed_to_fetch_ci_info", error=str(e), ticket_id=ticket_id)
            return None

    async def create_validation_session(
        self,
        work_package_id: UUID,
    ) -> ValidationSession:
        """Create a validation session for a work package"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status != WorkflowStatus.APPROVED:
            raise ValueError(
                f"Cannot start validation from status: {work_package.status}. "
                "Work package must be approved first."
            )

        # Update work package status
        work_package.status = WorkflowStatus.PENDING_VALIDATION

        # Create validation session
        session = ValidationSession(
            work_package_id=work_package_id,
            status="in_progress",
            started_at=datetime.utcnow(),
        )
        self.db.add(session)
        self.db.flush()

        # Fetch CI info from ServiceNow if this is a ServiceNow-triggered change
        ci_info = None
        if work_package.trigger_source and 'servicenow' in work_package.trigger_source.value:
            ci_info = await self._fetch_ci_info(work_package.ticket_id)

        # Generate questions based on change type and description
        questions = get_questions_for_change_type(
            work_package.change_type,
            description=work_package.description or "",
            title=work_package.title or "",
            ci_info=ci_info
        )
        for q_data in questions:
            question = ValidationQuestion(
                session_id=session.id,
                question_key=q_data["question_key"],
                question_text=q_data["question_text"],
                question_type=q_data.get("question_type", ValidationQuestionType.TEXT),
                category=q_data.get("category"),
                is_required=q_data.get("is_required", True),
                options=q_data.get("options"),
                order=q_data.get("order", 0),
            )
            self.db.add(question)

        work_package.status = WorkflowStatus.VALIDATION_IN_PROGRESS
        self.db.commit()
        self.db.refresh(session)

        logger.info(
            "validation_session_created",
            session_id=str(session.id),
            work_package_id=str(work_package_id),
            change_type=work_package.change_type.value,
            question_count=len(questions),
        )

        return session

    async def get_validation_session(
        self,
        session_id: UUID,
    ) -> Optional[ValidationSession]:
        """Get a validation session by ID"""
        return self.db.query(ValidationSession).filter(
            ValidationSession.id == session_id
        ).first()

    async def get_session_for_work_package(
        self,
        work_package_id: UUID,
    ) -> Optional[ValidationSession]:
        """Get the most recent validation session for a work package"""
        return self.db.query(ValidationSession).filter(
            ValidationSession.work_package_id == work_package_id,
        ).order_by(ValidationSession.started_at.desc()).first()

    async def get_questions(
        self,
        session_id: UUID,
    ) -> List[ValidationQuestion]:
        """Get all questions for a validation session"""
        return self.db.query(ValidationQuestion).filter(
            ValidationQuestion.session_id == session_id
        ).order_by(ValidationQuestion.order).all()

    async def get_unanswered_questions(
        self,
        session_id: UUID,
    ) -> List[ValidationQuestion]:
        """Get unanswered questions for a session"""
        session = await self.get_validation_session(session_id)
        if not session:
            return []

        answered_question_ids = {
            r.question_id for r in session.responses
        }

        return [
            q for q in session.questions
            if q.id not in answered_question_ids and q.is_required
        ]

    async def submit_response(
        self,
        session_id: UUID,
        response_data: ValidationResponseCreate,
        responder_id: Optional[UUID] = None,
    ) -> ValidationResponse:
        """Submit a response to a validation question"""
        session = await self.get_validation_session(session_id)
        if not session:
            raise ValueError("Validation session not found")

        if session.status != "in_progress":
            raise ValueError(f"Cannot submit response to session in status: {session.status}")

        # Verify question exists and belongs to this session
        question = self.db.query(ValidationQuestion).filter(
            ValidationQuestion.id == response_data.question_id,
            ValidationQuestion.session_id == session_id,
        ).first()

        if not question:
            raise ValueError("Question not found in this session")

        # Check if already answered
        existing = self.db.query(ValidationResponse).filter(
            ValidationResponse.session_id == session_id,
            ValidationResponse.question_id == response_data.question_id,
        ).first()

        if existing:
            # Update existing response
            existing.response_text = response_data.response_text
            existing.response_data = response_data.response_data
            existing.responded_at = datetime.utcnow()
            response = existing
        else:
            # Create new response
            response = ValidationResponse(
                session_id=session_id,
                question_id=response_data.question_id,
                response_text=response_data.response_text,
                response_data=response_data.response_data,
                responded_by=responder_id,
            )
            self.db.add(response)

        self.db.commit()
        self.db.refresh(response)

        # Check if all required questions are answered
        await self._check_session_completion(session_id)

        logger.info(
            "validation_response_submitted",
            session_id=str(session_id),
            question_key=question.question_key,
        )

        return response

    async def submit_multiple_responses(
        self,
        session_id: UUID,
        responses: List[ValidationResponseCreate],
        responder_id: Optional[UUID] = None,
    ) -> List[ValidationResponse]:
        """Submit multiple responses at once"""
        submitted = []
        for response_data in responses:
            response = await self.submit_response(
                session_id, response_data, responder_id
            )
            submitted.append(response)
        return submitted

    async def _check_session_completion(self, session_id: UUID) -> bool:
        """Check if all required questions are answered"""
        session = await self.get_validation_session(session_id)
        if not session:
            return False

        unanswered = await self.get_unanswered_questions(session_id)

        if not unanswered:
            session.all_questions_answered = True
            session.status = "completed"
            session.completed_at = datetime.utcnow()

            # Update work package status
            work_package = self.db.query(WorkPackage).filter(
                WorkPackage.id == session.work_package_id
            ).first()
            if work_package:
                work_package.status = WorkflowStatus.VALIDATED

            self.db.commit()

            logger.info(
                "validation_session_completed",
                session_id=str(session_id),
            )
            return True

        return False

    async def get_session_status(
        self,
        session_id: UUID,
    ) -> Dict[str, Any]:
        """Get detailed status of a validation session"""
        session = await self.get_validation_session(session_id)
        if not session:
            return {"error": "Session not found"}

        questions = await self.get_questions(session_id)
        unanswered = await self.get_unanswered_questions(session_id)

        answered_count = len(questions) - len(unanswered)
        total_required = sum(1 for q in questions if q.is_required)

        return {
            "session_id": str(session.id),
            "status": session.status,
            "total_questions": len(questions),
            "required_questions": total_required,
            "answered_questions": answered_count,
            "unanswered_required": len(unanswered),
            "all_questions_answered": session.all_questions_answered,
            "can_proceed": session.all_questions_answered,
            "started_at": session.started_at.isoformat() if session.started_at else None,
            "completed_at": session.completed_at.isoformat() if session.completed_at else None,
            "unanswered_questions": [
                {
                    "id": str(q.id),
                    "question_key": q.question_key,
                    "question_text": q.question_text,
                    "category": q.category,
                }
                for q in unanswered
            ],
        }

    async def fail_validation(
        self,
        session_id: UUID,
        reason: str,
    ) -> ValidationSession:
        """Mark validation as failed"""
        session = await self.get_validation_session(session_id)
        if not session:
            raise ValueError("Validation session not found")

        session.status = "failed"
        session.completed_at = datetime.utcnow()

        # Update work package status
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == session.work_package_id
        ).first()
        if work_package:
            work_package.status = WorkflowStatus.VALIDATION_FAILED

        self.db.commit()
        self.db.refresh(session)

        logger.warning(
            "validation_session_failed",
            session_id=str(session_id),
            reason=reason,
        )

        return session

    async def get_responses_summary(
        self,
        session_id: UUID,
    ) -> Dict[str, Any]:
        """Get summary of all responses for a session"""
        session = await self.get_validation_session(session_id)
        if not session:
            return {"error": "Session not found"}

        responses_by_category: Dict[str, List[Dict]] = {}

        for question in session.questions:
            category = question.category or "other"
            if category not in responses_by_category:
                responses_by_category[category] = []

            response = next(
                (r for r in session.responses if r.question_id == question.id),
                None
            )

            responses_by_category[category].append({
                "question_key": question.question_key,
                "question_text": question.question_text,
                "is_required": question.is_required,
                "answered": response is not None,
                "response": response.response_text if response else None,
            })

        return {
            "session_id": str(session.id),
            "status": session.status,
            "responses_by_category": responses_by_category,
        }

    async def restart_validation(
        self,
        session_id: UUID,
        regenerate_questions: bool = True,
    ) -> ValidationSession:
        """Restart a validation session - clear responses, regenerate questions"""
        session = await self.get_validation_session(session_id)
        if not session:
            raise ValueError("Validation session not found")

        # Clear all responses
        self.db.query(ValidationResponse).filter(
            ValidationResponse.session_id == session_id
        ).delete()

        # Get work package
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == session.work_package_id
        ).first()

        if regenerate_questions and work_package:
            # Clear old questions
            self.db.query(ValidationQuestion).filter(
                ValidationQuestion.session_id == session_id
            ).delete()

            # Fetch CI info from ServiceNow if applicable
            ci_info = None
            if work_package.trigger_source and 'servicenow' in work_package.trigger_source.value:
                ci_info = await self._fetch_ci_info(work_package.ticket_id)

            # Generate new questions based on description
            questions = get_questions_for_change_type(
                work_package.change_type,
                description=work_package.description or "",
                title=work_package.title or "",
                ci_info=ci_info
            )

            for q_data in questions:
                question = ValidationQuestion(
                    session_id=session.id,
                    question_key=q_data["question_key"],
                    question_text=q_data["question_text"],
                    question_type=q_data.get("question_type", ValidationQuestionType.TEXT),
                    category=q_data.get("category"),
                    is_required=q_data.get("is_required", True),
                    options=q_data.get("options"),
                    order=q_data.get("order", 0),
                )
                self.db.add(question)

        # Reset session status
        session.status = "in_progress"
        session.all_questions_answered = False
        session.completed_at = None
        session.started_at = datetime.utcnow()

        # Reset work package status
        if work_package:
            work_package.status = WorkflowStatus.VALIDATION_IN_PROGRESS

        self.db.commit()
        self.db.refresh(session)

        logger.info(
            "validation_session_restarted",
            session_id=str(session_id),
            questions_regenerated=regenerate_questions,
        )

        return session
