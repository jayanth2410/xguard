"""Review API endpoints"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.review import ReviewCreate, ReviewResponse
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

    return {
        "items": packages,
        "total": len(packages),
        "page": page,
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


@router.get("/{review_id}", response_model=ReviewResponse)
async def get_review(
    review_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a review by ID"""
    service = CheckerService(db)
    review = await service.get_review(review_id)

    if not review:
        raise HTTPException(status_code=404, detail="Review not found")

    return review


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


@router.post("/{work_package_id}/comment")
async def add_review_comment(
    work_package_id: UUID,
    reviewer_id: UUID,
    comment: str,
    comment_type: str = "general",
    db: Session = Depends(get_db),
):
    """Add a comment to an in-progress review"""
    service = CheckerService(db)

    try:
        review = await service.add_review_comment(
            work_package_id, reviewer_id, comment, comment_type
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return {"status": "comment_added", "review_id": str(review.id)}
