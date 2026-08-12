"""Dynamic clarification questions based on change type and task description"""
from typing import Dict, List, Any, Optional
import re
from app.models.enums import ChangeType, ClarificationQuestionType


# Backup-specific questions
BACKUP_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "backup_source_path",
        "question_text": "Confirm the source path to backup",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "backup",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., /var/log",
    },
    {
        "question_key": "backup_destination_path",
        "question_text": "Confirm the backup destination path",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "backup",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., /backup/WeekNo_Year",
    },
    {
        "question_key": "backup_schedule",
        "question_text": "Confirm the backup schedule (day/time/timezone)",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "backup",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., Sunday 10:00 AM IST",
    },
    {
        "question_key": "backup_retention",
        "question_text": "What is the backup retention policy? (how many backups to keep)",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "backup",
        "is_required": True,
        "order": 4,
        "placeholder": "e.g., Keep last 4 weeks",
    },
    {
        "question_key": "backup_disk_space",
        "question_text": "Is there sufficient disk space on the destination? (current free space)",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "backup",
        "is_required": True,
        "order": 5,
        "placeholder": "e.g., 50GB free on /backup",
    },
]


# Service restart questions
SERVICE_RESTART_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "service_name",
        "question_text": "Confirm the service name to restart",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "service",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., nginx, apache, mysql",
    },
    {
        "question_key": "service_downtime",
        "question_text": "Expected downtime during restart?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "service",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., 10-30 seconds",
    },
    {
        "question_key": "service_dependencies",
        "question_text": "What services depend on this service?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "service",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., API gateway, web frontend",
    },
]


# Minimal common questions (only essential ones)
COMMON_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "confirm_target_server",
        "question_text": "Confirm the target server (hostname/IP)",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common",
        "is_required": True,
        "order": 100,
    },
    {
        "question_key": "emergency_contact",
        "question_text": "Emergency contact for escalation",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common",
        "is_required": True,
        "order": 101,
    },
    {
        "question_key": "approved_execution_window",
        "question_text": "Confirm the approved execution window and timezone",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common", "is_required": True, "order": 102,
    },
    {
        "question_key": "expected_impact_downtime",
        "question_text": "Confirm the expected impact or downtime",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common", "is_required": True, "order": 103,
    },
    {
        "question_key": "rollback_ready",
        "question_text": "Confirm the rollback method or restoration point to use",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common", "is_required": True, "order": 104,
    },
    {
        "question_key": "success_verification",
        "question_text": "How will successful execution be verified?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common", "is_required": True, "order": 105,
    },
    {
        "question_key": "oncall_notified",
        "question_text": "Has the monitoring or on-call team been notified?",
        "question_type": ClarificationQuestionType.CONFIRMATION,
        "category": "common", "is_required": True, "order": 106,
    },
    {
        "question_key": "approval_reference",
        "question_text": "Provide the related approval or reference number, if required",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "common", "is_required": False, "order": 107,
    },
]


def detect_task_type(description: str, title: str = "") -> str:
    """Detect the specific task type from description/title"""
    combined = f"{description} {title}".lower()

    if 'backup' in combined or 'archive' in combined:
        return 'backup'
    elif 'restart' in combined or 'reboot' in combined:
        return 'restart'
    elif 'deploy' in combined or 'release' in combined:
        return 'deploy'
    elif 'patch' in combined or 'update' in combined:
        return 'patch'
    elif 'firewall' in combined or 'acl' in combined:
        return 'firewall'
    elif 'certificate' in combined or 'cert' in combined or 'ssl' in combined:
        return 'certificate'
    else:
        return 'generic'


def extract_info_from_description(description: str) -> Dict[str, str]:
    """Extract relevant info from description for pre-filling"""
    info = {}

    # Extract paths
    from_match = re.search(r'from\s+([/\w\-\.]+)', description, re.IGNORECASE)
    if from_match:
        info['source_path'] = from_match.group(1)

    to_match = re.search(r'to\s+([/\w\-\.<>]+)', description, re.IGNORECASE)
    if to_match:
        info['dest_path'] = to_match.group(1)

    # Extract schedule
    days = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
    for day in days:
        if day in description.lower():
            info['schedule_day'] = day.capitalize()
            break

    # Extract time
    time_match = re.search(r'(\d{1,2})[:\.](\d{2})\s*(AM|PM|am|pm)?', description)
    if time_match:
        info['schedule_time'] = f"{time_match.group(1)}:{time_match.group(2)} {time_match.group(3) or ''}".strip()

    # Extract timezone
    tz_match = re.search(r'(IST|UTC|EST|PST|GMT|CST)', description, re.IGNORECASE)
    if tz_match:
        info['timezone'] = tz_match.group(1).upper()

    return info


# Task-specific question mappings
TASK_TYPE_QUESTIONS: Dict[str, List[Dict[str, Any]]] = {
    'backup': BACKUP_QUESTIONS,
    'restart': SERVICE_RESTART_QUESTIONS,
}


# Network change questions
NETWORK_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "network_device_hostname_ip",
        "question_text": "Specify the device hostname and management IP",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "network",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., fw-dc1-01 / 10.1.1.1",
    },
    {
        "question_key": "network_ports_vlans_acls",
        "question_text": "List the ports/VLANs/ACLs being modified",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "network",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., VLAN 100, ACL permit-web",
    },
    {
        "question_key": "network_maintenance_window",
        "question_text": "Is there a maintenance window coordinated with NOC?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "network",
        "is_required": True,
        "order": 3,
        "placeholder": "Date, Time, NOC Ticket#",
    },
    {
        "question_key": "network_traffic_impact",
        "question_text": "What is the expected traffic impact during the change?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "network",
        "is_required": True,
        "order": 4,
        "placeholder": "e.g., 30 sec downtime, no impact",
    },
]


# Server change questions
SERVER_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "server_hostname_ip",
        "question_text": "Provide server hostname and IP address",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "server",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., srv-app-01 / 192.168.1.10",
    },
    {
        "question_key": "server_reboot_required",
        "question_text": "Is a reboot required? If yes, estimated downtime?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "server",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., Yes, 5 mins / No",
    },
    {
        "question_key": "server_services_affected",
        "question_text": "What services will be affected during this change?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "server",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., Apache, MySQL, Redis",
    },
    {
        "question_key": "server_backup_timestamp",
        "question_text": "Is there a recent backup? Provide backup timestamp",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "server",
        "is_required": True,
        "order": 4,
        "placeholder": "e.g., 2024-01-15 02:00 UTC",
    },
]


# Database change questions
DATABASE_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "db_name_server_port",
        "question_text": "Specify database name, server, and port",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "database",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., prod_db / db-srv-01:5432",
    },
    {
        "question_key": "db_tables_schemas",
        "question_text": "What tables/schemas will be modified?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "database",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., users, orders, schema_v2",
    },
    {
        "question_key": "db_recovery_available",
        "question_text": "Is a transaction/point-in-time recovery available?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "database",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., WAL enabled, last backup timestamp",
    },
    {
        "question_key": "db_row_count_lock_duration",
        "question_text": "Estimated row count and lock duration?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "database",
        "is_required": True,
        "order": 4,
        "placeholder": "e.g., 10M rows, 2 min lock",
    },
]


# Cloud change questions
CLOUD_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "cloud_account_region",
        "question_text": "Specify cloud account/subscription and region",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "cloud",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., AWS prod-123 / us-east-1",
    },
    {
        "question_key": "cloud_resources",
        "question_text": "List resources being created/modified/deleted",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "cloud",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., EC2 i-xxx, SG sg-xxx",
    },
    {
        "question_key": "cloud_iam_roles",
        "question_text": "IAM roles/policies impacted? List them",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "cloud",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., role-app-prod, policy-s3",
    },
    {
        "question_key": "cloud_terraform_state",
        "question_text": "Is Terraform state locked? Provide state bucket",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "cloud",
        "is_required": True,
        "order": 4,
        "placeholder": "e.g., s3://tf-state-prod/",
    },
]


# Application change questions
APPLICATION_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "app_name_version",
        "question_text": "Specify application name and version being deployed",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "application",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., payment-service v2.3.1",
    },
    {
        "question_key": "app_deployment_strategy",
        "question_text": "What deployment strategy will be used?",
        "question_type": ClarificationQuestionType.SELECT,
        "category": "application",
        "is_required": True,
        "order": 2,
        "options": ["Rolling", "Blue-Green", "Canary", "Recreate"],
    },
    {
        "question_key": "app_health_checks",
        "question_text": "What health checks will verify successful deployment?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "application",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., /health endpoint, smoke tests",
    },
    {
        "question_key": "app_feature_flags",
        "question_text": "Are there feature flags to control rollout?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "application",
        "is_required": False,
        "order": 4,
        "placeholder": "e.g., FF_NEW_CHECKOUT=true",
    },
]


# Security change questions
SECURITY_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "security_change_type",
        "question_text": "What type of security change is being made?",
        "question_type": ClarificationQuestionType.SELECT,
        "category": "security",
        "is_required": True,
        "order": 1,
        "options": ["IAM Policy", "Firewall Rule", "Certificate", "Secret Rotation", "Access Control"],
    },
    {
        "question_key": "security_scope",
        "question_text": "What is the scope of this security change?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "security",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., Production VPC, All API servers",
    },
    {
        "question_key": "security_approval",
        "question_text": "Has this been approved by the Security team?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "security",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., SEC-2024-001, approved by John Doe",
    },
    {
        "question_key": "security_audit_trail",
        "question_text": "How will this change be audited?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "security",
        "is_required": True,
        "order": 4,
        "placeholder": "e.g., CloudTrail, SIEM integration",
    },
]


# Container/K8s change questions
CONTAINER_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "k8s_cluster_namespace",
        "question_text": "Specify Kubernetes cluster and namespace",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "container",
        "is_required": True,
        "order": 1,
        "placeholder": "e.g., prod-cluster / payment-ns",
    },
    {
        "question_key": "k8s_resources",
        "question_text": "What Kubernetes resources will be modified?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "container",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., Deployment/api, Service/api-svc",
    },
    {
        "question_key": "k8s_replica_count",
        "question_text": "Current and desired replica count?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "container",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., 3 -> 5 replicas",
    },
    {
        "question_key": "k8s_resource_limits",
        "question_text": "Are resource limits/requests being changed?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "container",
        "is_required": False,
        "order": 4,
        "placeholder": "e.g., CPU: 500m->1000m, Memory: 512Mi->1Gi",
    },
]


# Monitoring change questions
MONITORING_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question_key": "monitoring_system",
        "question_text": "Which monitoring system is being modified?",
        "question_type": ClarificationQuestionType.SELECT,
        "category": "monitoring",
        "is_required": True,
        "order": 1,
        "options": ["Prometheus", "Grafana", "Datadog", "Splunk", "CloudWatch", "Other"],
    },
    {
        "question_key": "monitoring_alerts_affected",
        "question_text": "Which alerts/dashboards will be affected?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "monitoring",
        "is_required": True,
        "order": 2,
        "placeholder": "e.g., API-Latency-Alert, System-Dashboard",
    },
    {
        "question_key": "monitoring_oncall_notified",
        "question_text": "Has the on-call team been notified?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "monitoring",
        "is_required": True,
        "order": 3,
        "placeholder": "e.g., Yes, notified @oncall-sre",
    },
    {
        "question_key": "monitoring_silence_window",
        "question_text": "Is a silence/maintenance window needed?",
        "question_type": ClarificationQuestionType.TEXT,
        "category": "monitoring",
        "is_required": False,
        "order": 4,
        "placeholder": "e.g., Silence for 30 mins during deployment",
    },
]


# Mapping of change types to their specific questions
CHANGE_TYPE_QUESTIONS: Dict[ChangeType, List[Dict[str, Any]]] = {
    ChangeType.NETWORK: NETWORK_QUESTIONS,
    ChangeType.SERVER: SERVER_QUESTIONS,
    ChangeType.DATABASE: DATABASE_QUESTIONS,
    ChangeType.CLOUD: CLOUD_QUESTIONS,
    ChangeType.APPLICATION: APPLICATION_QUESTIONS,
    ChangeType.SECURITY: SECURITY_QUESTIONS,
    ChangeType.CONTAINER: CONTAINER_QUESTIONS,
    ChangeType.MONITORING: MONITORING_QUESTIONS,
}


def get_questions_for_change_type(
    change_type: ChangeType,
    description: str = "",
    title: str = "",
    ci_info: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    """Get clarification questions based on change type and task description"""

    # Detect specific task type from description
    task_type = detect_task_type(description, title)

    # Get task-specific questions if available
    if task_type in TASK_TYPE_QUESTIONS:
        specific_questions = TASK_TYPE_QUESTIONS[task_type].copy()
    else:
        # Fall back to change-type questions
        specific_questions = CHANGE_TYPE_QUESTIONS.get(change_type, []).copy()

    # Extract info from description for hints
    extracted_info = extract_info_from_description(description)

    # Pre-fill hints based on extracted info and CI
    for q in specific_questions:
        if q["question_key"] == "backup_source_path" and extracted_info.get("source_path"):
            q["placeholder"] = f"Detected: {extracted_info['source_path']}"
        elif q["question_key"] == "backup_destination_path" and extracted_info.get("dest_path"):
            q["placeholder"] = f"Detected: {extracted_info['dest_path']}"
        elif q["question_key"] == "backup_schedule":
            schedule_parts = []
            if extracted_info.get("schedule_day"):
                schedule_parts.append(extracted_info["schedule_day"])
            if extracted_info.get("schedule_time"):
                schedule_parts.append(extracted_info["schedule_time"])
            if extracted_info.get("timezone"):
                schedule_parts.append(extracted_info["timezone"])
            if schedule_parts:
                q["placeholder"] = f"Detected: {' '.join(schedule_parts)}"

    # Add CI info to common questions if available
    common_qs = [q.copy() for q in COMMON_QUESTIONS]
    if ci_info:
        common_qs = [
            q for q in common_qs if q["question_key"] != "confirm_target_server"
        ]
        for q in common_qs:
            if q["question_key"] == "confirm_target_server" and ci_info.get("ci_name"):
                q["placeholder"] = f"From ServiceNow CI: {ci_info['ci_name']}"

    all_questions = specific_questions + common_qs
    return sorted(all_questions, key=lambda q: q["order"])


def get_all_question_categories() -> List[str]:
    """Get all question categories"""
    categories = set()
    for questions in CHANGE_TYPE_QUESTIONS.values():
        for q in questions:
            categories.add(q["category"])
    categories.add("common")
    return list(categories)

