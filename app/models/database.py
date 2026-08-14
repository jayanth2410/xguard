"""SQLAlchemy database models"""
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, DateTime, Text, Boolean,
    ForeignKey, JSON, Enum as SQLEnum, Float, TypeDecorator
)
from sqlalchemy.orm import relationship, DeclarativeBase
import uuid


class UUID(TypeDecorator):
    """Platform-independent UUID type that works with SQLite and PostgreSQL"""
    impl = String(36)
    cache_ok = True

    def __init__(self, as_uuid=True):
        self.as_uuid = as_uuid
        super().__init__()

    def process_bind_param(self, value, dialect):
        if value is not None:
            return str(value)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and self.as_uuid:
            return uuid.UUID(value)
        return value

from app.models.enums import (
    ChangeType, WorkflowStatus, ExecutionMode,
    RiskLevel, TriggerSource
)


class Base(DeclarativeBase):
    pass


class User(Base):
    """User model for makers, checkers, and executors"""
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(String(50), nullable=False)  # maker, checker, executor, admin
    department = Column(String(100))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    created_packages = relationship("WorkPackage", back_populates="maker", foreign_keys="WorkPackage.maker_id")
    reviews = relationship("Review", back_populates="reviewer")
    executions = relationship("ExecutionRecord", back_populates="executor")


class WorkPackage(Base):
    """Main work package created by the AI Maker"""
    __tablename__ = "work_packages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    ticket_id = Column(String(50), nullable=False, index=True)  # ServiceNow ticket ID
    title = Column(String(500), nullable=False)
    description = Column(Text)

    # Classification
    change_type = Column(SQLEnum(ChangeType), nullable=False)
    trigger_source = Column(SQLEnum(TriggerSource), nullable=False)
    execution_mode = Column(SQLEnum(ExecutionMode), default=ExecutionMode.MANUAL)
    risk_level = Column(SQLEnum(RiskLevel), default=RiskLevel.AMBER)

    # Status tracking
    status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.DRAFT, index=True)

    # AI-generated content
    generated_code = Column(Text)  # Scripts, commands, code
    generated_procedure = Column(Text)  # Step-by-step implementation guide
    impact_analysis = Column(JSON)  # Impact analysis with RAG classification
    rollback_procedure = Column(Text)
    pre_checks = Column(JSON)  # Pre-execution checks
    post_checks = Column(JSON)  # Post-execution validation
    variables = Column(JSON)  # Variables like host/IP
    ai_questions = Column(JSON, default=list)  # Pre-review clarification questions
    ai_question_responses = Column(JSON, default=list)  # Answers keyed by question_key
    tokens_used = Column(Integer, nullable=False, default=0)  # Cumulative AI tokens
    monthly_tokens_used = Column(Integer, nullable=False, default=0)
    token_usage_month = Column(String(7))  # UTC YYYY-MM bucket

    # Target information
    target_infrastructure = Column(JSON)  # Infrastructure targets
    target_hosts = Column(JSON)  # List of hosts/IPs

    # Scheduling
    scheduled_start = Column(DateTime)
    scheduled_end = Column(DateTime)
    maintenance_window = Column(String(255))

    # Ownership
    maker_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))
    assigned_checker_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    maker = relationship("User", back_populates="created_packages", foreign_keys=[maker_id])
    assigned_checker = relationship("User", foreign_keys=[assigned_checker_id])
    reviews = relationship("Review", back_populates="work_package", cascade="all, delete-orphan")
    execution_records = relationship("ExecutionRecord", back_populates="work_package", cascade="all, delete-orphan")


class Review(Base):
    """Human checker review records"""
    __tablename__ = "reviews"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_package_id = Column(UUID(as_uuid=True), ForeignKey("work_packages.id"), nullable=False)
    reviewer_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    # Review details
    decision = Column(String(50), nullable=False)  # approved, rejected, rework_required
    comments = Column(Text)
    code_review_notes = Column(Text)
    rollback_review_notes = Column(Text)
    security_review_notes = Column(Text)
    impact_review_notes = Column(Text)

    # Execution control review
    approved_execution_mode = Column(SQLEnum(ExecutionMode))

    # Timestamps
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)

    # Relationships
    work_package = relationship("WorkPackage", back_populates="reviews")
    reviewer = relationship("User", back_populates="reviews")


class ExecutionRecord(Base):
    """Records of change execution"""
    __tablename__ = "execution_records"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    work_package_id = Column(UUID(as_uuid=True), ForeignKey("work_packages.id"), nullable=False)
    executor_id = Column(UUID(as_uuid=True), ForeignKey("users.id"))

    # Execution details
    execution_mode = Column(SQLEnum(ExecutionMode), nullable=False)
    status = Column(String(50), default="pending")  # pending, running, success, failed, rolled_back

    # JIT verification
    jit_verification_passed = Column(Boolean)
    jit_verification_details = Column(JSON)

    # Execution results
    output_log = Column(Text)
    error_log = Column(Text)
    exit_code = Column(Integer)
    command_log = Column(JSON)  # List of executed commands with timestamps and outputs

    # Rollback
    rollback_initiated = Column(Boolean, default=False)
    rollback_status = Column(String(50))
    rollback_log = Column(Text)

    # Timing
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    duration_seconds = Column(Float)

    # Relationships
    work_package = relationship("WorkPackage", back_populates="execution_records")
    executor = relationship("User", back_populates="executions")
