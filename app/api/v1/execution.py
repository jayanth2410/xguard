"""Execution API endpoints"""
from typing import Optional, List
from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.execution import ExecutionRequest, ExecutionResponse
from app.services.execution_service import ExecutionService
from app.services.remote_executor import RemoteExecutor, ConnectionConfig, LocalExecutor
from app.services.servicenow_service import servicenow
from app.models.database import WorkPackage, ExecutionRecord

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
    command: str
    timeout: int = 300


@router.post("/start", response_model=ExecutionResponse, status_code=201)
async def start_execution(
    request: ExecutionRequest,
    executor_id: Optional[UUID] = None,
    db: Session = Depends(get_db),
):
    """Start executing a validated work package"""
    service = ExecutionService(db)

    try:
        execution = await service.start_execution(request, executor_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return execution


@router.get("/{execution_id}", response_model=ExecutionResponse)
async def get_execution(
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """Get an execution record by ID"""
    service = ExecutionService(db)
    execution = await service.get_execution(execution_id)

    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")

    return execution


@router.get("/{execution_id}/status")
async def get_execution_status(
    execution_id: UUID,
    db: Session = Depends(get_db),
):
    """Get detailed execution status"""
    service = ExecutionService(db)
    status = await service.get_execution_status(execution_id)

    if "error" in status:
        raise HTTPException(status_code=404, detail=status["error"])

    return status


@router.get("/work-package/{work_package_id}")
async def get_executions_for_work_package(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get all executions for a work package"""
    service = ExecutionService(db)
    executions = await service.get_executions_for_work_package(work_package_id)

    return {
        "work_package_id": str(work_package_id),
        "execution_count": len(executions),
        "executions": [
            await service.get_execution_status(e.id)
            for e in executions
        ],
    }


class CommandLogEntry(BaseModel):
    """Single command log entry"""
    command: str
    output: str = ""
    exit_code: int = 0
    success: bool = True
    timestamp: str = ""
    host: str = ""


class CommandLogRequest(BaseModel):
    """Request to log a command"""
    work_package_id: str
    command: str
    output: str = ""
    stderr: str = ""
    exit_code: int = 0
    success: bool = True
    host: str = ""


class CompleteExecutionRequest(BaseModel):
    """Request to complete execution"""
    close_servicenow: bool = True
    close_notes: str = ""
    command_log: List[CommandLogEntry] = []


@router.post("/{work_package_id}/log-command")
async def log_command(
    work_package_id: UUID,
    request: CommandLogRequest,
    db: Session = Depends(get_db),
):
    """Log a command execution to the work package"""
    work_package = db.query(WorkPackage).filter(WorkPackage.id == work_package_id).first()
    if not work_package:
        raise HTTPException(status_code=404, detail="Work package not found")

    # Get or create execution record
    execution = db.query(ExecutionRecord).filter(
        ExecutionRecord.work_package_id == work_package_id
    ).order_by(ExecutionRecord.started_at.desc()).first()

    if not execution:
        from app.models.enums import ExecutionMode
        execution = ExecutionRecord(
            work_package_id=work_package_id,
            execution_mode=work_package.execution_mode or ExecutionMode.MANUAL,
            status="running",
            started_at=datetime.utcnow(),
            command_log=[]
        )
        db.add(execution)

    # Add command to log
    command_entry = {
        "command": request.command,
        "output": request.output,
        "stderr": request.stderr,
        "exit_code": request.exit_code,
        "success": request.success,
        "host": request.host,
        "timestamp": datetime.utcnow().isoformat()
    }

    current_log = execution.command_log or []
    current_log.append(command_entry)
    execution.command_log = current_log

    # Update output log
    output_line = f"[{command_entry['timestamp']}] $ {request.command}\n{request.output}"
    if request.stderr:
        output_line += f"\nSTDERR: {request.stderr}"
    output_line += f"\nExit: {request.exit_code}\n"

    execution.output_log = (execution.output_log or "") + output_line

    db.commit()

    return {
        "success": True,
        "logged_commands": len(current_log),
        "message": "Command logged successfully"
    }


@router.get("/{work_package_id}/command-log")
async def get_command_log(
    work_package_id: UUID,
    db: Session = Depends(get_db),
):
    """Get the command log for a work package"""
    execution = db.query(ExecutionRecord).filter(
        ExecutionRecord.work_package_id == work_package_id
    ).order_by(ExecutionRecord.started_at.desc()).first()

    if not execution:
        return {"work_package_id": str(work_package_id), "commands": [], "count": 0}

    return {
        "work_package_id": str(work_package_id),
        "execution_id": str(execution.id),
        "commands": execution.command_log or [],
        "count": len(execution.command_log or []),
        "output_log": execution.output_log
    }


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

    # Save command log if provided
    if request and request.command_log:
        execution = db.query(ExecutionRecord).filter(
            ExecutionRecord.work_package_id == work_package_id
        ).order_by(ExecutionRecord.started_at.desc()).first()

        if execution:
            # Build execution log summary for ServiceNow
            log_entries = []
            for cmd in request.command_log:
                log_entries.append({
                    "command": cmd.command,
                    "output": cmd.output,
                    "exit_code": cmd.exit_code,
                    "success": cmd.success,
                    "timestamp": cmd.timestamp or datetime.utcnow().isoformat(),
                    "host": cmd.host
                })
            execution.command_log = log_entries
            db.commit()

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
):
    """Execute a command on a remote host via SSH or WinRM"""
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
):
    """Execute a multi-line script on a remote host"""
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

        return {
            "success": result.success,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "host": request.host,
        }

    finally:
        executor.disconnect()


@router.post("/local/execute")
async def execute_local_command(
    command: str,
    timeout: int = 300,
):
    """Execute a command locally (for testing)"""
    executor = LocalExecutor()
    result = executor.execute(command, timeout=timeout)

    return {
        "success": result.success,
        "exit_code": result.exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }


class ScriptExecutionRequest(BaseModel):
    """Request to create and execute script remotely"""
    work_package_id: str
    host: str
    port: int = 22
    username: str
    password: str = ""
    private_key: str = ""
    connection_type: str = "ssh"
    script_content: str
    change_type: str = "server"
    variables: dict = {}
    dry_run: bool = False
    timeout: int = 600


@router.post("/script/create-and-execute")
async def create_and_execute_script(
    request: ScriptExecutionRequest,
    db: Session = Depends(get_db),
):
    """Create script on remote host and execute it"""
    from app.services.script_manager import script_manager

    config = ConnectionConfig(
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        private_key=request.private_key if request.private_key else None,
        connection_type=request.connection_type,
    )

    result = await script_manager.create_and_execute(
        connection=config,
        script_content=request.script_content,
        work_package_id=request.work_package_id,
        change_type=request.change_type,
        variables=request.variables,
        dry_run=request.dry_run
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Execution failed"))

    return result


class ScriptCreateRequest(BaseModel):
    """Request to create script on remote host"""
    work_package_id: str
    host: str
    port: int = 22
    username: str
    password: str = ""
    private_key: str = ""
    connection_type: str = "ssh"
    script_content: str
    change_type: str = "server"
    variables: dict = {}


@router.post("/script/create")
async def create_remote_script(
    request: ScriptCreateRequest,
):
    """Create script file on remote host without executing"""
    from app.services.script_manager import script_manager

    config = ConnectionConfig(
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        private_key=request.private_key if request.private_key else None,
        connection_type=request.connection_type,
    )

    # Prepare script
    extension = "ps1" if request.connection_type == "winrm" else "sh"
    filename = script_manager.generate_script_filename(
        request.work_package_id,
        request.change_type,
        extension
    )

    prepared_script = script_manager.prepare_script_content(
        request.script_content,
        request.change_type,
        request.variables,
        request.connection_type
    )

    result = await script_manager.create_remote_script(
        config,
        prepared_script,
        filename
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Script creation failed"))

    return result


class ScriptExecuteRequest(BaseModel):
    """Request to execute existing script on remote host"""
    host: str
    port: int = 22
    username: str
    password: str = ""
    private_key: str = ""
    connection_type: str = "ssh"
    script_path: str
    timeout: int = 600


@router.post("/script/execute")
async def execute_existing_script(
    request: ScriptExecuteRequest,
):
    """Execute an existing script on remote host"""
    from app.services.script_manager import script_manager

    config = ConnectionConfig(
        host=request.host,
        port=request.port,
        username=request.username,
        password=request.password,
        private_key=request.private_key if request.private_key else None,
        connection_type=request.connection_type,
    )

    result = await script_manager.execute_remote_script(
        config,
        request.script_path,
        request.timeout
    )

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Execution failed"))

    return result
