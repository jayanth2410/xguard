"""ServiceNow Integration API endpoints"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.servicenow_service import servicenow, SNTableType
from app.services.maker_service import MakerService
from app.schemas.work_package import WorkPackageCreate
from app.models.enums import ChangeType, TriggerSource

router = APIRouter()


class ImportRecordRequest(BaseModel):
    """Request to import record as work package"""
    record_number: str
    record_type: str = "incident"  # incident, change_request, request
    change_type: ChangeType


@router.get("/test-connection")
async def test_servicenow_connection():
    """Test connection to ServiceNow"""
    result = await servicenow.test_connection()
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result.get("error", "Connection failed"))
    return result


# ============ INCIDENTS ============

@router.get("/incidents")
async def get_incidents(
    query: str = "",
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """Get list of incidents from ServiceNow"""
    incidents = await servicenow.get_incidents(query=query, limit=limit, offset=offset)
    return {
        "type": "incident",
        "records": incidents,
        "count": len(incidents),
        "limit": limit,
        "offset": offset
    }


@router.get("/incidents/pending")
async def get_pending_incidents():
    """Get incidents pending action"""
    incidents = await servicenow.get_pending_incidents()
    return {
        "type": "incident",
        "records": incidents,
        "count": len(incidents)
    }


@router.get("/incidents/{incident_number}")
async def get_incident(incident_number: str):
    """Get specific incident from ServiceNow"""
    incident = await servicenow.get_incident(incident_number)
    if not incident:
        raise HTTPException(status_code=404, detail="Incident not found")
    return incident


# ============ CHANGE REQUESTS ============

@router.get("/changes")
async def get_change_requests(
    query: str = "",
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """Get list of change requests from ServiceNow"""
    changes = await servicenow.get_change_requests(query=query, limit=limit, offset=offset)
    return {
        "type": "change_request",
        "records": changes,
        "count": len(changes),
        "limit": limit,
        "offset": offset
    }


@router.get("/changes/pending")
async def get_pending_changes():
    """Get change requests pending approval"""
    changes = await servicenow.get_pending_changes()
    return {
        "type": "change_request",
        "records": changes,
        "count": len(changes)
    }


@router.get("/changes/{change_number}")
async def get_change_request(change_number: str):
    """Get specific change request from ServiceNow"""
    change = await servicenow.get_change_request(change_number)
    if not change:
        raise HTTPException(status_code=404, detail="Change request not found")
    return change


# ============ SERVICE REQUESTS ============

@router.get("/requests")
async def get_service_requests(
    query: str = "",
    limit: int = Query(50, le=200),
    offset: int = 0
):
    """Get list of service requests from ServiceNow"""
    requests = await servicenow.get_requests(query=query, limit=limit, offset=offset)
    return {
        "type": "sc_request",
        "records": requests,
        "count": len(requests),
        "limit": limit,
        "offset": offset
    }


@router.get("/requests/{request_number}")
async def get_service_request(request_number: str):
    """Get specific service request from ServiceNow"""
    req = await servicenow.get_request(request_number)
    if not req:
        raise HTTPException(status_code=404, detail="Service request not found")
    return req


# ============ IMPORT & ACTIONS ============

@router.post("/import")
async def import_record_as_work_package(
    request: ImportRecordRequest,
    db: Session = Depends(get_db)
):
    """Import ServiceNow record (incident/change/request) as a work package"""

    # Determine table type and get record
    if request.record_type == "incident":
        record = await servicenow.get_incident(request.record_number)
        trigger_source = TriggerSource.SERVICENOW_INCIDENT
    elif request.record_type == "change_request":
        record = await servicenow.get_change_request(request.record_number)
        trigger_source = TriggerSource.SERVICENOW_CHANGE
    elif request.record_type == "request":
        record = await servicenow.get_request(request.record_number)
        trigger_source = TriggerSource.SERVICENOW_REQUEST
    else:
        raise HTTPException(status_code=400, detail=f"Invalid record type: {request.record_type}")

    if not record:
        raise HTTPException(status_code=404, detail=f"{request.record_type} not found in ServiceNow")

    # Parse record to work package format
    wp_data = servicenow.parse_record_to_work_package(record, request.record_type)

    # Create work package
    work_package_create = WorkPackageCreate(
        ticket_id=wp_data["ticket_id"],
        title=wp_data["title"],
        description=wp_data["description"],
        change_type=request.change_type,
        trigger_source=trigger_source,
        variables={
            "servicenow": wp_data.get("servicenow_details", {}),
            "servicenow_sys_id": wp_data.get("servicenow_sys_id", ""),
            "record_type": request.record_type,
        },
    )

    service = MakerService(db)
    work_package = await service.create_work_package(work_package_create)

    # Add work notes to ServiceNow
    table_type = SNTableType.INCIDENT if request.record_type == "incident" else \
                 SNTableType.CHANGE_REQUEST if request.record_type == "change_request" else \
                 SNTableType.REQUEST

    await servicenow.add_work_notes(
        record["sys_id"],
        f"Work package created in Maker-Checker Platform. ID: {work_package.id}",
        table_type
    )

    return {
        "success": True,
        "work_package_id": str(work_package.id),
        "ticket_id": work_package.ticket_id,
        "record_type": request.record_type,
        "message": f"{request.record_type} {request.record_number} imported successfully"
    }


