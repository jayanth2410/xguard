"""Work Package API endpoints"""
from typing import Optional, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.enums import WorkflowStatus, ChangeType
from app.schemas.work_package import (
    WorkPackageCreate,
    WorkPackageUpdate,
    WorkPackageResponse,
    WorkPackageListResponse,
)
from app.services.maker_service import MakerService

router = APIRouter()


@router.post("/", response_model=WorkPackageResponse, status_code=201)
async def create_work_package(
    data: WorkPackageCreate,
    db: Session = Depends(get_db),
):
    """Create a new work package"""
    service = MakerService(db)
    work_package = await service.create_work_package(data)
    return work_package


@router.get("/", response_model=WorkPackageListResponse)
async def list_work_packages(
    status: Optional[WorkflowStatus] = None,
    change_type: Optional[ChangeType] = None,
    ticket_id: Optional[str] = Query(None, max_length=50),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List work packages with optional filters"""
    service = MakerService(db)
    skip = (page - 1) * page_size

    items = await service.list_work_packages(
        status=status,
        change_type=change_type,
        ticket_id=ticket_id,
        skip=skip,
        limit=page_size,
    )

    # Get total count for pagination
    from app.models.database import WorkPackage
    query = db.query(WorkPackage)
    if status:
        query = query.filter(WorkPackage.status == status)
    if change_type:
        query = query.filter(WorkPackage.change_type == change_type)
    if ticket_id:
        query = query.filter(WorkPackage.ticket_id.ilike(f"%{ticket_id.strip()}%"))
    total = query.count()

    return WorkPackageListResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/{work_package_id}", response_model=WorkPackageResponse)
async def get_work_package(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get a work package by ID"""
    service = MakerService(db)
    work_package = await service.get_work_package(work_package_id)

    if not work_package:
        raise HTTPException(status_code=404, detail="Work package not found")

    return work_package


@router.put("/{work_package_id}", response_model=WorkPackageResponse)
async def update_work_package(
    work_package_id: UUID,
    data: WorkPackageUpdate,
    db: Session = Depends(get_db),
):
    """Update a work package"""
    service = MakerService(db)

    try:
        work_package = await service.update_work_package(work_package_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if not work_package:
        raise HTTPException(status_code=404, detail="Work package not found")

    return work_package


@router.post("/{work_package_id}/submit", response_model=WorkPackageResponse)
async def submit_for_review(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Submit work package for human review"""
    service = MakerService(db)

    try:
        work_package = await service.submit_for_review(work_package_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return work_package


