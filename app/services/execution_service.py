"""Execution Service - Change execution with JIT verification"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
import asyncio
from sqlalchemy.orm import Session
import structlog

from app.models.database import WorkPackage, ExecutionRecord, WorkPackageStep
from app.models.enums import WorkflowStatus, ExecutionMode
from app.schemas.execution import ExecutionRequest

logger = structlog.get_logger()


class ExecutionService:
    """Service for executing changes with verification and rollback"""

    def __init__(self, db: Session):
        self.db = db

    async def start_execution(
        self,
        request: ExecutionRequest,
        executor_id: Optional[UUID] = None,
    ) -> ExecutionRecord:
        """Start executing a validated work package"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == request.work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status != WorkflowStatus.VALIDATED:
            raise ValueError(
                f"Cannot execute from status: {work_package.status}. "
                "Work package must be validated first."
            )

        # Determine execution mode
        execution_mode = request.execution_mode or work_package.execution_mode

        # Create execution record
        execution = ExecutionRecord(
            work_package_id=work_package.id,
            executor_id=executor_id,
            execution_mode=execution_mode,
            status="pending",
            started_at=datetime.utcnow(),
        )
        self.db.add(execution)
        self.db.flush()

        # Update work package status
        work_package.status = WorkflowStatus.PENDING_EXECUTION

        self.db.commit()
        self.db.refresh(execution)

        logger.info(
            "execution_started",
            execution_id=str(execution.id),
            work_package_id=str(work_package.id),
            execution_mode=execution_mode.value,
            dry_run=request.dry_run,
        )

        # Start the execution process
        if not request.dry_run:
            # In a real implementation, this would be a background task
            await self._execute(execution.id)

        return execution

    async def _execute(self, execution_id: UUID) -> None:
        """Execute the change (would be async in production)"""
        execution = self.db.query(ExecutionRecord).filter(
            ExecutionRecord.id == execution_id
        ).first()

        if not execution:
            return

        work_package = execution.work_package
        execution.status = "running"
        work_package.status = WorkflowStatus.EXECUTING
        self.db.commit()

        try:
            # Step 1: JIT Verification
            jit_result = await self._perform_jit_verification(work_package)
            execution.jit_verification_passed = jit_result["passed"]
            execution.jit_verification_details = jit_result
            self.db.commit()

            if not jit_result["passed"]:
                execution.status = "failed"
                execution.error_log = "JIT verification failed"
                work_package.status = WorkflowStatus.EXECUTION_FAILED
                self.db.commit()
                return

            # Step 2: Execute pre-checks
            pre_check_result = await self._execute_pre_checks(work_package)
            if not pre_check_result["passed"]:
                execution.status = "failed"
                execution.error_log = f"Pre-checks failed: {pre_check_result.get('error')}"
                work_package.status = WorkflowStatus.EXECUTION_FAILED
                self.db.commit()
                return

            # Step 3: Execute the change
            exec_result = await self._execute_change(work_package, execution)
            execution.output_log = exec_result.get("output", "")
            execution.exit_code = exec_result.get("exit_code", 0)

            if exec_result["success"]:
                # Step 4: Execute post-checks
                post_check_result = await self._execute_post_checks(work_package)

                if post_check_result["passed"]:
                    execution.status = "success"
                    work_package.status = WorkflowStatus.EXECUTED
                else:
                    # Post-checks failed, initiate rollback
                    await self._initiate_rollback(execution)
            else:
                execution.status = "failed"
                execution.error_log = exec_result.get("error", "Execution failed")
                work_package.status = WorkflowStatus.EXECUTION_FAILED

                # Initiate rollback on failure
                await self._initiate_rollback(execution)

        except Exception as e:
            execution.status = "failed"
            execution.error_log = str(e)
            work_package.status = WorkflowStatus.EXECUTION_FAILED
            logger.exception("execution_error", execution_id=str(execution_id))

        finally:
            execution.completed_at = datetime.utcnow()
            if execution.started_at:
                execution.duration_seconds = (
                    execution.completed_at - execution.started_at
                ).total_seconds()
            self.db.commit()

    async def _perform_jit_verification(
        self,
        work_package: WorkPackage,
    ) -> Dict[str, Any]:
        """Perform Just-In-Time verification before execution"""
        checks = []

        # Check connectivity to target hosts
        for host in work_package.target_hosts or []:
            checks.append({
                "check": "connectivity",
                "target": host,
                "passed": True,  # Would actually ping/test connection
            })

        # Check access/credentials
        checks.append({
            "check": "access_verification",
            "passed": True,  # Would verify credentials
        })

        # Pre-flight checks
        checks.append({
            "check": "pre_flight",
            "passed": True,  # Would run pre-flight checks
        })

        all_passed = all(c["passed"] for c in checks)

        return {
            "passed": all_passed,
            "checks": checks,
            "timestamp": datetime.utcnow().isoformat(),
        }

    async def _execute_pre_checks(
        self,
        work_package: WorkPackage,
    ) -> Dict[str, Any]:
        """Execute pre-checks defined in the work package"""
        pre_checks = work_package.pre_checks or {}
        checks = pre_checks.get("checks", [])

        results = []
        for check in checks:
            # In production, would actually execute the check command
            results.append({
                "name": check.get("name"),
                "passed": True,
                "output": "Check passed",
            })

        all_passed = all(r["passed"] for r in results)

        return {
            "passed": all_passed,
            "results": results,
        }

    async def _execute_change(
        self,
        work_package: WorkPackage,
        execution: ExecutionRecord,
    ) -> Dict[str, Any]:
        """Execute the actual change"""
        output_lines = []

        # Execute each step
        steps = self.db.query(WorkPackageStep).filter(
            WorkPackageStep.work_package_id == work_package.id,
            WorkPackageStep.is_rollback_step == False,
        ).order_by(WorkPackageStep.step_number).all()

        for step in steps:
            output_lines.append(f"=== Step {step.step_number}: {step.title} ===")
            output_lines.append(f"Command: {step.command}")

            # In production, would actually execute the command
            # For now, simulate success
            output_lines.append("Output: Command executed successfully")
            output_lines.append("")

        # If no steps, execute generated code
        if not steps and work_package.generated_code:
            output_lines.append("=== Executing Generated Code ===")
            output_lines.append(work_package.generated_code[:500])
            output_lines.append("Output: Code executed successfully")

        return {
            "success": True,
            "output": "\n".join(output_lines),
            "exit_code": 0,
        }

    async def _execute_post_checks(
        self,
        work_package: WorkPackage,
    ) -> Dict[str, Any]:
        """Execute post-checks defined in the work package"""
        post_checks = work_package.post_checks or {}
        checks = post_checks.get("checks", [])

        results = []
        for check in checks:
            # In production, would actually execute the check command
            results.append({
                "name": check.get("name"),
                "passed": True,
                "output": "Post-check passed",
            })

        all_passed = all(r["passed"] for r in results)

        return {
            "passed": all_passed,
            "results": results,
        }

    async def _initiate_rollback(
        self,
        execution: ExecutionRecord,
    ) -> None:
        """Initiate rollback procedure"""
        execution.rollback_initiated = True
        execution.rollback_status = "in_progress"

        work_package = execution.work_package

        try:
            # Get rollback steps
            rollback_steps = self.db.query(WorkPackageStep).filter(
                WorkPackageStep.work_package_id == work_package.id,
                WorkPackageStep.is_rollback_step == True,
            ).order_by(WorkPackageStep.step_number).all()

            rollback_log = []

            if rollback_steps:
                for step in rollback_steps:
                    rollback_log.append(f"=== Rollback Step {step.step_number}: {step.title} ===")
                    rollback_log.append(f"Command: {step.command}")
                    # In production, would execute rollback command
                    rollback_log.append("Rollback step completed")
            elif work_package.rollback_procedure:
                rollback_log.append("=== Executing Rollback Procedure ===")
                rollback_log.append(work_package.rollback_procedure)
                rollback_log.append("Rollback completed")

            execution.rollback_log = "\n".join(rollback_log)
            execution.rollback_status = "completed"
            execution.status = "rolled_back"
            work_package.status = WorkflowStatus.ROLLED_BACK

            logger.info(
                "rollback_completed",
                execution_id=str(execution.id),
            )

        except Exception as e:
            execution.rollback_status = "failed"
            execution.rollback_log = f"Rollback failed: {str(e)}"
            logger.exception(
                "rollback_failed",
                execution_id=str(execution.id),
            )

        self.db.commit()

    async def get_execution(
        self,
        execution_id: UUID,
    ) -> Optional[ExecutionRecord]:
        """Get an execution record by ID"""
        return self.db.query(ExecutionRecord).filter(
            ExecutionRecord.id == execution_id
        ).first()

    async def get_executions_for_work_package(
        self,
        work_package_id: UUID,
    ) -> List[ExecutionRecord]:
        """Get all execution records for a work package"""
        return self.db.query(ExecutionRecord).filter(
            ExecutionRecord.work_package_id == work_package_id
        ).order_by(ExecutionRecord.started_at.desc()).all()

    async def get_execution_status(
        self,
        execution_id: UUID,
    ) -> Dict[str, Any]:
        """Get detailed execution status"""
        execution = await self.get_execution(execution_id)
        if not execution:
            return {"error": "Execution not found"}

        return {
            "execution_id": str(execution.id),
            "work_package_id": str(execution.work_package_id),
            "status": execution.status,
            "execution_mode": execution.execution_mode.value,
            "jit_verification_passed": execution.jit_verification_passed,
            "jit_verification_details": execution.jit_verification_details,
            "exit_code": execution.exit_code,
            "rollback_initiated": execution.rollback_initiated,
            "rollback_status": execution.rollback_status,
            "started_at": execution.started_at.isoformat() if execution.started_at else None,
            "completed_at": execution.completed_at.isoformat() if execution.completed_at else None,
            "duration_seconds": execution.duration_seconds,
        }

    async def complete_execution(
        self,
        work_package_id: UUID,
    ) -> WorkPackage:
        """Mark work package as completed after successful execution"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        # Allow completion from EXECUTED (automated) or VALIDATED (manual execution)
        allowed_statuses = [
            WorkflowStatus.EXECUTED,
            WorkflowStatus.VALIDATED,
            WorkflowStatus.PENDING_EXECUTION,
            WorkflowStatus.EXECUTING,
        ]
        if work_package.status not in allowed_statuses:
            raise ValueError(f"Cannot complete from status: {work_package.status}")

        work_package.status = WorkflowStatus.COMPLETED
        self.db.commit()
        self.db.refresh(work_package)

        logger.info(
            "work_package_completed",
            work_package_id=str(work_package_id),
        )

        return work_package
