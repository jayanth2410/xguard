"""Execution API endpoints"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.services.execution_service import ExecutionService
from app.services.remote_executor import RemoteExecutor, ConnectionConfig
from app.services.servicenow_service import servicenow
from app.models.database import WorkPackage, ExecutionRecord
from app.models.enums import ExecutionMode, WorkflowStatus

router = APIRouter()


class RemoteConnectionRequest(BaseModel):
    """Request to connect to remote host"""
    host: str
    port: int = 22
    username: str
    password: str = ""
    private_key: str = ""
    connection_type: str = "ssh"  # ssh or winrm


class RemoteCommandRequest(BaseModel):
    """Request to execute remote command"""
    host: str
    port: int = 22
    username: str
    password: str = ""
    private_key: str = ""
    connection_type: str = "ssh"
    work_package_id: UUID
    is_rollback: bool = False
    rollback_complete: bool = False
    command: str
    timeout: int = 300


class CommandLogEntry(BaseModel):
    """Single command log entry"""
    command: str
    output: str = ""
    exit_code: int = 0
    success: bool = True
    timestamp: str = ""
    host: str = ""


class CompleteExecutionRequest(BaseModel):
    """Request to complete execution"""
    close_servicenow: bool = True
    close_notes: str = ""
    command_log: List[CommandLogEntry] = Field(default_factory=list)


def _get_authorized_work_package(db: Session, work_package_id: UUID, *, is_rollback: bool = False) -> WorkPackage:
    """Enforce reviewer approval before a remote command is run."""
    work_package = db.query(WorkPackage).filter(WorkPackage.id == work_package_id).first()
    if not work_package:
        raise HTTPException(status_code=404, detail="Work package not found")
    if is_rollback:
        allowed = {
            WorkflowStatus.EXECUTION_FAILED,
            WorkflowStatus.EXECUTING,
            WorkflowStatus.ROLLED_BACK,
        }
        message = "Rollback is only allowed after execution has started or failed."
    else:
        allowed = {WorkflowStatus.APPROVED, WorkflowStatus.PENDING_EXECUTION, WorkflowStatus.EXECUTING}
        message = f"Cannot execute from status: {work_package.status.value}. The work package must be approved by a reviewer first."
    if work_package.status not in allowed:
        raise HTTPException(status_code=409, detail=message)
    return work_package


def _record_remote_result(
    db,
    work_package,
    request,
    result,
    executor_id: Optional[UUID] = None,
) -> None:
    """Persist execution state immediately; do not depend on client-side logging."""
    execution = db.query(ExecutionRecord).filter(ExecutionRecord.work_package_id == work_package.id).order_by(ExecutionRecord.started_at.desc()).first()
    if not execution or execution.status in {"success", "rolled_back"}:
        execution = ExecutionRecord(work_package_id=work_package.id, executor_id=executor_id, execution_mode=work_package.execution_mode or ExecutionMode.MANUAL, status="running", started_at=datetime.utcnow(), command_log=[])
        db.add(execution)
    elif executor_id and not execution.executor_id:
        execution.executor_id = executor_id
    entry = {"command": request.command, "output": result.stdout, "stderr": result.stderr, "exit_code": result.exit_code, "success": result.success, "host": request.host, "is_rollback": request.is_rollback, "timestamp": datetime.utcnow().isoformat()}
    log = list(execution.command_log or [])
    log.append(entry)
    execution.command_log = log
    execution.exit_code = result.exit_code
    execution.output_log = (execution.output_log or "") + f"\n$ {request.command}\n{result.stdout}\n{result.stderr}".rstrip()
    if request.is_rollback:
        execution.rollback_initiated = True
        execution.rollback_status = "in_progress" if result.success else "failed"
        if result.success and request.rollback_complete:
            execution.rollback_status = "completed"
            execution.status = "rolled_back"
            execution.completed_at = datetime.utcnow()
            work_package.status = WorkflowStatus.ROLLED_BACK
        execution.rollback_log = (execution.rollback_log or "") + f"\n$ {request.command}\n{result.stdout}\n{result.stderr}".rstrip()
    elif result.success:
        execution.status = "running"
        work_package.status = WorkflowStatus.EXECUTING
    else:
        execution.status = "failed"
        execution.error_log = result.stderr or result.stdout or "Remote execution failed"
        work_package.status = WorkflowStatus.EXECUTION_FAILED
    db.commit()

@router.post("/{work_package_id}/complete")
async def complete_execution(
    work_package_id: UUID,
    request: Optional[CompleteExecutionRequest] = None,
    db: Session = Depends(get_db),
):
    """Mark work package as completed and optionally close ServiceNow ticket"""
    service = ExecutionService(db)

    # Get work package for ticket info
    work_package = db.query(WorkPackage).filter(WorkPackage.id == work_package_id).first()
    if not work_package:
        raise HTTPException(status_code=404, detail="Work package not found")

    # The server-side execution log is authoritative. Never replace it with
    # client-supplied history during completion.
    execution = db.query(ExecutionRecord).filter(
        ExecutionRecord.work_package_id == work_package_id
    ).order_by(ExecutionRecord.started_at.desc()).first()

    try:
        completed_package = await service.complete_execution(work_package_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    result = {
        "work_package_id": str(work_package_id),
        "status": completed_package.status.value,
        "message": "Work package completed successfully",
    }

    # Close ServiceNow ticket if requested and ticket is from ServiceNow
    if request is None or request.close_servicenow:
        ticket_id = work_package.ticket_id
        if ticket_id and (ticket_id.startswith("CHG") or ticket_id.startswith("INC") or ticket_id.startswith("REQ")):
            # Build close notes with execution summary
            close_notes = request.close_notes if request else ""
            if not close_notes:
                # Get execution log for notes
                execution = db.query(ExecutionRecord).filter(
                    ExecutionRecord.work_package_id == work_package_id
                ).order_by(ExecutionRecord.started_at.desc()).first()

                if execution and execution.command_log:
                    cmd_count = len(execution.command_log)
                    success_count = sum(1 for c in execution.command_log if c.get("success", True))
                    close_notes = f"Executed via Maker-Checker Platform\n"
                    close_notes += f"Commands executed: {cmd_count}\n"
                    close_notes += f"Successful: {success_count}\n"
                    if execution.duration_seconds:
                        close_notes += f"Duration: {execution.duration_seconds:.1f}s"
                else:
                    close_notes = "Change implemented via Maker-Checker Platform"

            # Close the ServiceNow ticket
            sn_result = await servicenow.close_ticket(ticket_id, close_notes)
            result["servicenow"] = sn_result

            # Add execution log to ServiceNow work notes
            if execution and execution.output_log:
                await servicenow.add_execution_log(ticket_id, f"=== Execution Log ===\n{execution.output_log[:3500]}")

    return result


@router.post("/remote/test-connection")
async def test_remote_connection(
    request: RemoteConnectionRequest,
):
    """Test connection to a remote host"""
    config = ConnectionConfig(
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        private_key=request.private_key if request.private_key else None,
        connection_type=request.connection_type,
    )

    executor = RemoteExecutor(config)
    connected = executor.connect()

    if connected:
        executor.disconnect()
        return {
            "success": True,
            "message": f"Successfully connected to {request.host} via {request.connection_type.upper()}",
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect to {request.host} via {request.connection_type.upper()}"
        )


@router.post("/remote/execute")
async def execute_remote_command(
    request: RemoteCommandRequest,
    db: Session = Depends(get_db),
    executor_id: Optional[UUID] = Header(None, alias="X-XGuard-User-Id"),
):
    """Execute a command on a remote host via SSH or WinRM"""
    work_package = _get_authorized_work_package(
        db, request.work_package_id, is_rollback=request.is_rollback
    )
    config = ConnectionConfig(
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        private_key=request.private_key if request.private_key else None,
        connection_type=request.connection_type,
    )

    executor = RemoteExecutor(config)

    try:
        if not executor.connect():
            raise HTTPException(
                status_code=400,
                detail=f"Failed to connect to {request.host}"
            )

        result = executor.execute(request.command, timeout=request.timeout)
        _record_remote_result(db, work_package, request, result, executor_id)

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "host": request.host,
            "command": request.command,
        }

    finally:
        executor.disconnect()


@router.post("/remote/execute-script")
async def execute_remote_script(
    request: RemoteCommandRequest,
    db: Session = Depends(get_db),
    executor_id: Optional[UUID] = Header(None, alias="X-XGuard-User-Id"),
):
    """Execute a multi-line script on a remote host"""
    work_package = _get_authorized_work_package(
        db, request.work_package_id, is_rollback=request.is_rollback
    )
    config = ConnectionConfig(
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        private_key=request.private_key if request.private_key else None,
        connection_type=request.connection_type,
    )

    executor = RemoteExecutor(config)

    try:
        if not executor.connect():
            raise HTTPException(
                status_code=400,
                detail=f"Failed to connect to {request.host}"
            )

        result = executor.execute_script(request.command, timeout=request.timeout)
        _record_remote_result(db, work_package, request, result, executor_id)

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "host": request.host,
        }

    finally:
        executor.disconnect()


