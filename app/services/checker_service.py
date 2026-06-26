"""Human Checker Service - Expert review and approval"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.models.database import WorkPackage, Review, User
from app.models.enums import WorkflowStatus, ExecutionMode
from app.schemas.review import ReviewCreate, ReviewDecision

logger = structlog.get_logger()


class CheckerService:
    """Service for human review and approval of work packages"""

    def __init__(self, db: Session):
        self.db = db

    async def get_pending_reviews(
        self,
        checker_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkPackage]:
        """Get work packages pending review"""
        query = self.db.query(WorkPackage).filter(
            WorkPackage.status.in_([
                WorkflowStatus.PENDING_REVIEW,
                WorkflowStatus.IN_REVIEW,
            ])
        )

        if checker_id:
            query = query.filter(WorkPackage.assigned_checker_id == checker_id)

        return query.order_by(WorkPackage.created_at.asc()).offset(skip).limit(limit).all()

    async def start_review(
        self,
        work_package_id: UUID,
        reviewer_id: UUID,
    ) -> Review:
        """Start reviewing a work package"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status != WorkflowStatus.PENDING_REVIEW:
            raise ValueError(f"Cannot start review from status: {work_package.status}")

        # Update work package status
        work_package.status = WorkflowStatus.IN_REVIEW
        work_package.assigned_checker_id = reviewer_id

        # Create review record
        review = Review(
            work_package_id=work_package_id,
            reviewer_id=reviewer_id,
            decision="in_progress",
            started_at=datetime.utcnow(),
        )
        self.db.add(review)
        self.db.commit()
        self.db.refresh(review)

        logger.info(
            "review_started",
            work_package_id=str(work_package_id),
            reviewer_id=str(reviewer_id),
        )

        return review

    async def submit_review(
        self,
        review_data: ReviewCreate,
        reviewer_id: UUID,
    ) -> Review:
        """Submit a review decision"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == review_data.work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status != WorkflowStatus.IN_REVIEW:
            raise ValueError(f"Cannot submit review from status: {work_package.status}")

        # Find existing review or create new one
        review = self.db.query(Review).filter(
            Review.work_package_id == review_data.work_package_id,
            Review.reviewer_id == reviewer_id,
            Review.completed_at.is_(None),
        ).first()

        if not review:
            review = Review(
                work_package_id=review_data.work_package_id,
                reviewer_id=reviewer_id,
                started_at=datetime.utcnow(),
            )
            self.db.add(review)

        # Update review
        review.decision = review_data.decision.value
        review.comments = review_data.comments
        review.code_review_notes = review_data.code_review_notes
        review.security_review_notes = review_data.security_review_notes
        review.impact_review_notes = review_data.impact_review_notes
        review.approved_execution_mode = review_data.approved_execution_mode
        review.completed_at = datetime.utcnow()

        # Update work package status based on decision
        if review_data.decision == ReviewDecision.APPROVED:
            work_package.status = WorkflowStatus.APPROVED
            if review_data.approved_execution_mode:
                work_package.execution_mode = review_data.approved_execution_mode
        elif review_data.decision == ReviewDecision.REJECTED:
            work_package.status = WorkflowStatus.REJECTED
        elif review_data.decision == ReviewDecision.REWORK_REQUIRED:
            work_package.status = WorkflowStatus.REWORK_REQUIRED

        self.db.commit()
        self.db.refresh(review)

        logger.info(
            "review_submitted",
            work_package_id=str(review_data.work_package_id),
            reviewer_id=str(reviewer_id),
            decision=review_data.decision.value,
        )

        return review

    async def get_review(self, review_id: UUID) -> Optional[Review]:
        """Get a review by ID"""
        return self.db.query(Review).filter(Review.id == review_id).first()

    async def get_reviews_for_work_package(
        self,
        work_package_id: UUID,
    ) -> List[Review]:
        """Get all reviews for a work package"""
        return self.db.query(Review).filter(
            Review.work_package_id == work_package_id
        ).order_by(Review.started_at.desc()).all()

    async def get_review_summary(
        self,
        work_package_id: UUID,
    ) -> dict:
        """Get review summary for a work package"""
        reviews = await self.get_reviews_for_work_package(work_package_id)

        # Serialize reviews to dicts
        reviews_list = []
        for r in reviews:
            reviews_list.append({
                "id": str(r.id),
                "work_package_id": str(r.work_package_id),
                "reviewer_id": str(r.reviewer_id),
                "decision": r.decision,
                "comments": r.comments,
                "code_review_notes": r.code_review_notes,
                "security_review_notes": r.security_review_notes,
                "impact_review_notes": r.impact_review_notes,
                "approved_execution_mode": r.approved_execution_mode.value if r.approved_execution_mode else None,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
            })

        latest_review = reviews_list[0] if reviews_list else None

        return {
            "total_reviews": len(reviews),
            "approved": sum(1 for r in reviews if r.decision == "approved"),
            "rejected": sum(1 for r in reviews if r.decision == "rejected"),
            "rework_required": sum(1 for r in reviews if r.decision == "rework_required"),
            "latest_decision": reviews[0].decision if reviews else None,
            "latest_review": latest_review,
            "reviews": reviews_list,
        }

    async def add_review_comment(
        self,
        work_package_id: UUID,
        reviewer_id: UUID,
        comment: str,
        comment_type: str = "general",  # general, code, security, impact
    ) -> Review:
        """Add a comment to an in-progress review"""
        review = self.db.query(Review).filter(
            Review.work_package_id == work_package_id,
            Review.reviewer_id == reviewer_id,
            Review.completed_at.is_(None),
        ).first()

        if not review:
            raise ValueError("No active review found")

        if comment_type == "code":
            existing = review.code_review_notes or ""
            review.code_review_notes = f"{existing}\n{comment}".strip()
        elif comment_type == "security":
            existing = review.security_review_notes or ""
            review.security_review_notes = f"{existing}\n{comment}".strip()
        elif comment_type == "impact":
            existing = review.impact_review_notes or ""
            review.impact_review_notes = f"{existing}\n{comment}".strip()
        else:
            existing = review.comments or ""
            review.comments = f"{existing}\n{comment}".strip()

        self.db.commit()
        self.db.refresh(review)

        return review
