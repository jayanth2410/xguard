"""Validation API endpoints"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.validation import (
    ValidationSessionCreate,
    ValidationSessionResponse,
    ValidationResponseCreate,
)
from app.services.validation_service import ValidationService
from app.core.validation_questions import get_questions_for_change_type, CHANGE_TYPE_QUESTIONS
from app.models.enums import ChangeType, WorkflowStatus

router = APIRouter()


@router.post("/session", status_code=201)
async def create_validation_session(
    data: ValidationSessionCreate,
    db: Session = Depends(get_db),
):
    """Create a validation session for a work package"""
    service = ValidationService(db)

    try:
        session = await service.create_validation_session(data.work_package_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status = await service.get_session_status(session.id)

    return {
        "session_id": str(session.id),
        "work_package_id": str(data.work_package_id),
        "status": "created",
        "session_details": status,
    }


@router.get("/session/{session_id}")
async def get_validation_session(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """Get validation session details"""
    service = ValidationService(db)
    session = await service.get_validation_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Validation session not found")

    status = await service.get_session_status(session_id)
    return status


@router.get("/work-package/{work_package_id}/session")
async def get_session_for_work_package(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get the active validation session for a work package"""
    service = ValidationService(db)
    session = await service.get_session_for_work_package(work_package_id)

    if not session:
        raise HTTPException(status_code=404, detail="No active validation session found for this work package")

    status = await service.get_session_status(session.id)
    return status


@router.get("/session/{session_id}/questions")
async def get_session_questions(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """Get all questions for a validation session"""
    service = ValidationService(db)
    session = await service.get_validation_session(session_id)

    if not session:
        raise HTTPException(status_code=404, detail="Validation session not found")

    questions = await service.get_questions(session_id)

    return {
        "session_id": str(session_id),
        "questions": [
            {
                "id": str(q.id),
                "question_key": q.question_key,
                "question_text": q.question_text,
                "question_type": q.question_type.value,
                "category": q.category,
                "is_required": q.is_required,
                "options": q.options,
                "order": q.order,
            }
            for q in questions
        ],
    }


@router.get("/session/{session_id}/unanswered")
async def get_unanswered_questions(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """Get unanswered required questions"""
    service = ValidationService(db)

    unanswered = await service.get_unanswered_questions(session_id)

    return {
        "session_id": str(session_id),
        "unanswered_count": len(unanswered),
        "questions": [
            {
                "id": str(q.id),
                "question_key": q.question_key,
                "question_text": q.question_text,
                "category": q.category,
            }
            for q in unanswered
        ],
    }


@router.post("/session/{session_id}/respond")
async def submit_response(
    session_id: UUID,
    data: ValidationResponseCreate,
    responder_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """Submit a response to a validation question"""
    service = ValidationService(db)

    try:
        response = await service.submit_response(session_id, data, responder_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status = await service.get_session_status(session_id)

    return {
        "response_id": str(response.id),
        "session_status": status,
    }


@router.post("/session/{session_id}/respond-multiple")
async def submit_multiple_responses(
    session_id: UUID,
    responses: List[ValidationResponseCreate],
    responder_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """Submit multiple responses at once"""
    service = ValidationService(db)

    try:
        submitted = await service.submit_multiple_responses(
            session_id, responses, responder_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status = await service.get_session_status(session_id)

    return {
        "responses_submitted": len(submitted),
        "session_status": status,
    }


@router.get("/session/{session_id}/summary")
async def get_responses_summary(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """Get summary of all responses"""
    service = ValidationService(db)
    summary = await service.get_responses_summary(session_id)

    if "error" in summary:
        raise HTTPException(status_code=404, detail=summary["error"])

    return summary


@router.post("/session/{session_id}/fail")
async def fail_validation(
    session_id: UUID,
    reason: str,
    db: Session = Depends(get_db),
):
    """Mark validation as failed"""
    service = ValidationService(db)

    try:
        session = await service.fail_validation(session_id, reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {
        "session_id": str(session_id),
        "status": "failed",
        "reason": reason,
    }


@router.get("/questions/{change_type}")
async def get_questions_for_type(
    change_type: ChangeType,
):
    """Get validation questions for a specific change type"""
    questions = get_questions_for_change_type(change_type)

    return {
        "change_type": change_type.value,
        "question_count": len(questions),
        "questions": questions,
    }


@router.get("/questions")
async def get_all_question_types():
    """Get all available question types and categories"""
    return {
        "change_types": [ct.value for ct in ChangeType],
        "questions_by_type": {
            ct.value: len(get_questions_for_change_type(ct))
            for ct in ChangeType
        },
    }


@router.get("/queue")
async def get_validation_queue(
    db: Session = Depends(get_db),
):
    """Get work packages in validation states"""
    from app.models.database import WorkPackage, ValidationSession

    # Get work packages in validation-related states
    validation_statuses = [
        WorkflowStatus.APPROVED,
        WorkflowStatus.PENDING_VALIDATION,
        WorkflowStatus.VALIDATION_IN_PROGRESS,
        WorkflowStatus.VALIDATED,
        WorkflowStatus.VALIDATION_FAILED,
    ]

    work_packages = db.query(WorkPackage).filter(
        WorkPackage.status.in_(validation_statuses)
    ).order_by(WorkPackage.updated_at.desc()).all()

    items = []
    for wp in work_packages:
        # Get validation session progress
        session = db.query(ValidationSession).filter(
            ValidationSession.work_package_id == wp.id
        ).order_by(ValidationSession.started_at.desc()).first()

        progress = 0
        if session:
            total = len(session.questions) if session.questions else 0
            answered = len(session.responses) if session.responses else 0
            progress = int((answered / total * 100)) if total > 0 else 0

        items.append({
            "id": str(wp.id),
            "ticket_id": wp.ticket_id,
            "title": wp.title,
            "change_type": wp.change_type.value,
            "status": wp.status.value,
            "progress": progress,
            "updated_at": wp.updated_at.isoformat() if wp.updated_at else None,
        })

    # Calculate stats
    stats = {
        "pending": sum(1 for wp in work_packages if wp.status in [WorkflowStatus.APPROVED, WorkflowStatus.PENDING_VALIDATION]),
        "in_progress": sum(1 for wp in work_packages if wp.status == WorkflowStatus.VALIDATION_IN_PROGRESS),
        "validated": sum(1 for wp in work_packages if wp.status == WorkflowStatus.VALIDATED),
        "failed": sum(1 for wp in work_packages if wp.status == WorkflowStatus.VALIDATION_FAILED),
    }

    return {
        "items": items,
        "stats": stats,
        "total": len(items),
    }


@router.post("/session/{session_id}/restart")
async def restart_validation(
    session_id: UUID,
    db: Session = Depends(get_db),
):
    """Restart a validation session - clears responses and resets status"""
    service = ValidationService(db)

    try:
        session = await service.restart_validation(session_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    status = await service.get_session_status(session.id)
    return {
        "session_id": str(session.id),
        "status": "restarted",
        "session_details": status,
    }


@router.post("/work-package/{work_package_id}/reset")
async def reset_work_package_validation(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Reset work package back to APPROVED status to restart validation"""
    from app.models.database import WorkPackage

    work_package = db.query(WorkPackage).filter(
        WorkPackage.id == work_package_id
    ).first()

    if not work_package:
        raise HTTPException(status_code=404, detail="Work package not found")

    # Allow reset from validation states
    allowed_states = [
        WorkflowStatus.VALIDATION_IN_PROGRESS,
        WorkflowStatus.VALIDATION_FAILED,
        WorkflowStatus.PENDING_VALIDATION,
    ]

    if work_package.status not in allowed_states:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot reset from status: {work_package.status}. Must be in validation state."
        )

    work_package.status = WorkflowStatus.APPROVED
    db.commit()

    return {
        "work_package_id": str(work_package_id),
        "status": "reset",
        "new_status": "approved",
        "message": "Work package reset to APPROVED. You can now start a new validation session."
    }
