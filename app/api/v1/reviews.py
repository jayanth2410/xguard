"""Review API endpoints"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.review import ReviewCreate, ReviewDraft, ReviewResponse
from app.services.checker_service import CheckerService

router = APIRouter()


@router.get("/pending")
async def get_pending_reviews(
    checker_id: Optional[UUID] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get work packages pending review"""
    service = CheckerService(db)
    skip = (page - 1) * page_size

    packages = await service.get_pending_reviews(
        checker_id=checker_id,
        skip=skip,
        limit=page_size,
    )
    stats = await service.get_queue_stats()

    return {
        "items": packages,
        "total": len(packages),
        "page": page,
        "stats": stats,
    }


@router.post("/{work_package_id}/start", response_model=ReviewResponse)
async def start_review(
    work_package_id: UUID,
    reviewer_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Start reviewing a work package"""
    import uuid as uuid_module

    # Handle demo/missing reviewer_id - generate a demo UUID
    if not reviewer_id or reviewer_id == "demo-reviewer-id":
        actual_reviewer_id = uuid_module.UUID("00000000-0000-0000-0000-000000000001")
    else:
        try:
            actual_reviewer_id = uuid_module.UUID(reviewer_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid reviewer_id format")

    service = CheckerService(db)

    try:
        review = await service.start_review(work_package_id, actual_reviewer_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return review


@router.post("/submit", response_model=ReviewResponse)
async def submit_review(
    data: ReviewCreate,
    reviewer_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Submit a review decision"""
    import uuid as uuid_module

    # Handle demo/missing reviewer_id
    if not reviewer_id or reviewer_id == "demo-reviewer-id":
        actual_reviewer_id = uuid_module.UUID("00000000-0000-0000-0000-000000000001")
    else:
        try:
            actual_reviewer_id = uuid_module.UUID(reviewer_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid reviewer_id format")

    service = CheckerService(db)

    try:
        review = await service.submit_review(data, actual_reviewer_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return review


@router.put("/{work_package_id}/draft", response_model=ReviewResponse)
async def save_review_draft(
    work_package_id: UUID,
    data: ReviewDraft,
    reviewer_id: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Save review notes without submitting a decision."""
    import uuid as uuid_module

    if not reviewer_id or reviewer_id == "demo-reviewer-id":
        actual_reviewer_id = uuid_module.UUID("00000000-0000-0000-0000-000000000001")
    else:
        try:
            actual_reviewer_id = uuid_module.UUID(reviewer_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid reviewer_id format")

    try:
        return await CheckerService(db).save_review_draft(
            work_package_id, actual_reviewer_id, data
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/work-package/{work_package_id}")
async def get_reviews_for_work_package(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get all reviews for a work package"""
    service = CheckerService(db)
    reviews = await service.get_reviews_for_work_package(work_package_id)
    summary = await service.get_review_summary(work_package_id)

    return summary


