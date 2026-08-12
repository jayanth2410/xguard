"""AI Maker Service - Creates work packages with AI assistance"""
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime
from sqlalchemy.orm import Session
import structlog

from app.models.database import WorkPackage, WorkPackageStep, User
from app.models.enums import ChangeType, WorkflowStatus, ExecutionMode, RiskLevel, TriggerSource
from app.schemas.work_package import WorkPackageCreate, WorkPackageUpdate

logger = structlog.get_logger()


class MakerService:
    """Service for AI-assisted work package creation"""

    def __init__(self, db: Session):
        self.db = db

    async def create_work_package(
        self,
        data: WorkPackageCreate,
        maker_id: Optional[UUID] = None,
    ) -> WorkPackage:
        """Create a new work package"""
        work_package = WorkPackage(
            ticket_id=data.ticket_id,
            title=data.title,
            description=data.description,
            change_type=data.change_type,
            trigger_source=data.trigger_source,
            execution_mode=data.execution_mode,
            status=WorkflowStatus.DRAFT,
            generated_code=data.generated_code,
            generated_procedure=data.generated_procedure,
            impact_analysis=data.impact_analysis,
            rollback_procedure=data.rollback_procedure,
            pre_checks=data.pre_checks,
            post_checks=data.post_checks,
            variables=data.variables,
            ai_questions=data.ai_questions or [],
            ai_question_responses=data.ai_question_responses or [],
            target_infrastructure=data.target_infrastructure,
            target_hosts=data.target_hosts,
            scheduled_start=data.scheduled_start,
            scheduled_end=data.scheduled_end,
            maintenance_window=data.maintenance_window,
            maker_id=maker_id,
        )

        self.db.add(work_package)
        self.db.flush()

        # Add steps if provided
        if data.steps:
            for step_data in data.steps:
                step = WorkPackageStep(
                    work_package_id=work_package.id,
                    step_number=step_data.step_number,
                    title=step_data.title,
                    description=step_data.description,
                    command=step_data.command,
                    expected_output=step_data.expected_output,
                    timeout_seconds=step_data.timeout_seconds,
                    is_rollback_step=step_data.is_rollback_step,
                )
                self.db.add(step)

        self.db.commit()
        self.db.refresh(work_package)

        logger.info(
            "work_package_created",
            work_package_id=str(work_package.id),
            ticket_id=work_package.ticket_id,
            change_type=work_package.change_type.value,
        )

        return work_package

    async def update_work_package(
        self,
        work_package_id: UUID,
        data: WorkPackageUpdate,
    ) -> Optional[WorkPackage]:
        """Update an existing work package"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            return None

        # Only allow updates in certain statuses
        if work_package.status not in [
            WorkflowStatus.DRAFT,
            WorkflowStatus.REWORK_REQUIRED,
        ]:
            raise ValueError(f"Cannot update work package in status: {work_package.status}")

        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(work_package, field, value)

        self.db.commit()
        self.db.refresh(work_package)

        logger.info(
            "work_package_updated",
            work_package_id=str(work_package_id),
            updated_fields=list(update_data.keys()),
        )

        return work_package

    async def submit_for_review(self, work_package_id: UUID) -> WorkPackage:
        """Submit work package for human review"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        if work_package.status not in [
            WorkflowStatus.DRAFT,
            WorkflowStatus.REWORK_REQUIRED,
        ]:
            raise ValueError(f"Cannot submit for review from status: {work_package.status}")

        answers = {
            answer.get("question_key"): answer.get("response_text")
            for answer in (work_package.ai_question_responses or [])
            if answer.get("question_key") and str(answer.get("response_text", "")).strip()
        }
        unanswered = [
            question for question in (work_package.ai_questions or [])
            if question.get("is_required", True) and question.get("question_key") not in answers
        ]
        if unanswered:
            raise ValueError(f"Answer all required clarification questions before review ({len(unanswered)} remaining)")
        if not work_package.generated_code or not work_package.rollback_procedure:
            raise ValueError("Generate the final implementation and rollback code before review")

        work_package.status = WorkflowStatus.PENDING_REVIEW
        self.db.commit()
        self.db.refresh(work_package)

        logger.info(
            "work_package_submitted_for_review",
            work_package_id=str(work_package_id),
        )

        return work_package

    async def analyze_requirements(
        self,
        ticket_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Analyze ticket requirements and suggest change type and execution mode"""
        # This would integrate with an LLM to analyze the ticket
        # For now, return a placeholder analysis
        analysis = {
            "suggested_change_type": ChangeType.SERVER,
            "suggested_execution_mode": ExecutionMode.MANUAL,
            "complexity_score": 0.7,
            "risk_indicators": [],
            "recommended_checks": [],
        }

        logger.info("requirements_analyzed", ticket_id=ticket_data.get("ticket_id"))
        return analysis

    async def generate_implementation(
        self,
        work_package_id: UUID,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate implementation code, procedures, and checks using AI"""
        work_package = self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

        if not work_package:
            raise ValueError("Work package not found")

        # This would integrate with an LLM to generate implementation
        # For now, return placeholder content
        generated = {
            "code": self._generate_sample_code(work_package),
            "procedure": self._generate_sample_procedure(work_package),
            "pre_checks": self._generate_pre_checks(work_package),
            "post_checks": self._generate_post_checks(work_package),
            "rollback_procedure": self._generate_rollback_procedure(work_package),
            "impact_analysis": self._generate_impact_analysis(work_package),
        }

        # Update work package with generated content
        work_package.generated_code = generated["code"]
        work_package.generated_procedure = generated["procedure"]
        work_package.pre_checks = generated["pre_checks"]
        work_package.post_checks = generated["post_checks"]
        work_package.rollback_procedure = generated["rollback_procedure"]
        work_package.impact_analysis = generated["impact_analysis"]

        self.db.commit()
        self.db.refresh(work_package)

        logger.info(
            "implementation_generated",
            work_package_id=str(work_package_id),
        )

        return generated

    def _generate_sample_code(self, work_package: WorkPackage) -> str:
        """Generate sample code based on change type"""
        if work_package.change_type == ChangeType.SERVER:
            return """#!/bin/bash
# Server Change Script
# Variables: {{hostname}}, {{ip_address}}

set -e

echo "Starting server change on {{hostname}}"

# Pre-check
ssh {{ip_address}} "uptime"

# Execute change
ssh {{ip_address}} "sudo systemctl restart nginx"

# Post-check
ssh {{ip_address}} "sudo systemctl status nginx"

echo "Server change completed successfully"
"""
        elif work_package.change_type == ChangeType.DATABASE:
            return """-- Database Change Script
-- Variables: {{database}}, {{schema}}

BEGIN TRANSACTION;

-- Backup current state
CREATE TABLE {{schema}}.backup_table AS SELECT * FROM {{schema}}.target_table;

-- Apply changes
ALTER TABLE {{schema}}.target_table ADD COLUMN new_field VARCHAR(255);

-- Verify
SELECT COUNT(*) FROM {{schema}}.target_table;

COMMIT;
"""
        elif work_package.change_type == ChangeType.NETWORK:
            return """! Network Device Configuration
! Variables: {{device_hostname}}, {{vlan_id}}

configure terminal
interface Vlan{{vlan_id}}
 description New VLAN Configuration
 ip address {{ip_address}} {{subnet_mask}}
 no shutdown
exit
write memory
"""
        return "# Generated code placeholder"

    def _generate_sample_procedure(self, work_package: WorkPackage) -> str:
        """Generate implementation procedure"""
        return f"""# Implementation Procedure for {work_package.title}

## Pre-Implementation Steps
1. Verify all stakeholders have been notified
2. Confirm maintenance window with NOC
3. Take backup/snapshot of affected systems
4. Verify rollback procedure is ready

## Implementation Steps
1. Connect to target system
2. Execute pre-checks
3. Apply the change
4. Verify change was successful
5. Execute post-checks

## Post-Implementation Steps
1. Verify all services are functioning
2. Update documentation
3. Notify stakeholders of completion
4. Close change ticket
"""

    def _generate_pre_checks(self, work_package: WorkPackage) -> Dict[str, Any]:
        """Generate pre-execution checks"""
        return {
            "checks": [
                {
                    "name": "connectivity_check",
                    "description": "Verify connectivity to target systems",
                    "command": "ping -c 3 {{target_host}}",
                    "expected_result": "0% packet loss",
                },
                {
                    "name": "backup_verification",
                    "description": "Verify recent backup exists",
                    "command": "ls -la /backups/",
                    "expected_result": "Backup file from today",
                },
                {
                    "name": "service_status",
                    "description": "Check current service status",
                    "command": "systemctl status {{service_name}}",
                    "expected_result": "active (running)",
                },
            ]
        }

    def _generate_post_checks(self, work_package: WorkPackage) -> Dict[str, Any]:
        """Generate post-execution checks"""
        return {
            "checks": [
                {
                    "name": "service_running",
                    "description": "Verify service is running after change",
                    "command": "systemctl status {{service_name}}",
                    "expected_result": "active (running)",
                },
                {
                    "name": "health_check",
                    "description": "Verify application health endpoint",
                    "command": "curl -s http://{{target_host}}/health",
                    "expected_result": "HTTP 200",
                },
                {
                    "name": "log_check",
                    "description": "Check for errors in logs",
                    "command": "tail -100 /var/log/{{service}}.log | grep -i error",
                    "expected_result": "No errors",
                },
            ]
        }

    def _generate_rollback_procedure(self, work_package: WorkPackage) -> str:
        """Generate rollback procedure"""
        return f"""# Rollback Procedure for {work_package.title}

## Automatic Rollback
If the change fails, the following rollback steps will be executed automatically:

1. Stop the affected service
2. Restore from backup/snapshot
3. Restart the service
4. Verify service is functioning

## Manual Rollback Steps
If automatic rollback fails:

1. SSH to the affected system
2. Execute: `sudo systemctl stop {{service_name}}`
3. Restore backup: `sudo cp /backups/{{backup_file}} /current/location`
4. Start service: `sudo systemctl start {{service_name}}`
5. Verify: `sudo systemctl status {{service_name}}`
"""

    def _generate_impact_analysis(self, work_package: WorkPackage) -> Dict[str, Any]:
        """Generate impact analysis with RAG classification"""
        return {
            "risk_level": "amber",
            "impact_summary": f"This {work_package.change_type.value} change may affect dependent services",
            "affected_systems": work_package.target_hosts or [],
            "affected_services": [],
            "downtime_estimate": "5-10 minutes",
            "risk_factors": [
                {"factor": "Service dependency", "level": "amber"},
                {"factor": "Data integrity", "level": "green"},
                {"factor": "Security impact", "level": "green"},
            ],
            "mitigation_strategies": [
                "Implement during maintenance window",
                "Have rollback procedure ready",
                "Monitor closely for 30 minutes post-change",
            ],
        }

    async def get_work_package(self, work_package_id: UUID) -> Optional[WorkPackage]:
        """Get a work package by ID"""
        return self.db.query(WorkPackage).filter(
            WorkPackage.id == work_package_id
        ).first()

    async def list_work_packages(
        self,
        status: Optional[WorkflowStatus] = None,
        change_type: Optional[ChangeType] = None,
        ticket_id: Optional[str] = None,
        maker_id: Optional[UUID] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[WorkPackage]:
        """List work packages with optional filters"""
        query = self.db.query(WorkPackage)

        if status:
            query = query.filter(WorkPackage.status == status)
        if change_type:
            query = query.filter(WorkPackage.change_type == change_type)
        if ticket_id:
            query = query.filter(WorkPackage.ticket_id.ilike(f"%{ticket_id.strip()}%"))
        if maker_id:
            query = query.filter(WorkPackage.maker_id == maker_id)

        return query.order_by(WorkPackage.created_at.desc()).offset(skip).limit(limit).all()
