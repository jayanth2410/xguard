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
    REJECTED = "rejected"
    REWORK_REQUIRED = "rework_required"
    PENDING_VALIDATION = "pending_validation"
    VALIDATION_IN_PROGRESS = "validation_in_progress"
    VALIDATED = "validated"
    VALIDATION_FAILED = "validation_failed"
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


class ValidationQuestionType(str, Enum):
    """Types of validation questions"""
    TEXT = "text"
    SELECT = "select"
    MULTI_SELECT = "multi_select"
    DATE_TIME = "date_time"
    CONFIRMATION = "confirmation"


class InfrastructureTarget(str, Enum):
    """Infrastructure target types"""
    DATACENTER = "datacenter"
    NETWORK = "network"
    CLOUD_AWS = "cloud_aws"
    CLOUD_AZURE = "cloud_azure"
    CLOUD_GCP = "cloud_gcp"
    CONTAINER_K8S = "container_k8s"
    DATABASE = "database"
    SECURITY_IAM = "security_iam"
    END_USER_COMPUTING = "end_user_computing"
    MIDDLEWARE = "middleware"
    MONITORING = "monitoring"
    CICD = "cicd"
    BACKUP_DR = "backup_dr"
    APPLICATIONS = "applications"
