"""Enumerations for the Maker-Checker system"""
from enum import Enum


class ChangeType(str, Enum):
    """Types of infrastructure changes"""
    NETWORK = "network"
    SERVER = "server"
    DATABASE = "database"
    CLOUD = "cloud"
    APPLICATION = "application"
    SECURITY = "security"
    CONTAINER = "container"
    MONITORING = "monitoring"


class WorkflowStatus(str, Enum):
    """Status of a work package in the workflow"""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REWORK_REQUIRED = "rework_required"
    REJECTED = "rejected"
    PENDING_EXECUTION = "pending_execution"
    EXECUTING = "executing"
    EXECUTED = "executed"
    EXECUTION_FAILED = "execution_failed"
    ROLLED_BACK = "rolled_back"
    COMPLETED = "completed"


class ExecutionMode(str, Enum):
    """How the change will be executed"""
    AUTOMATED = "automated"
    MANUAL = "manual"


class RiskLevel(str, Enum):
    """Risk assessment levels (RAG)"""
    RED = "red"
    AMBER = "amber"
    GREEN = "green"


class TriggerSource(str, Enum):
    """Source of the change request"""
    SERVICENOW_INCIDENT = "servicenow_incident"
    SERVICENOW_CHANGE = "servicenow_change"
    SERVICENOW_REQUEST = "servicenow_request"
    MANUAL = "manual"
    API = "api"
