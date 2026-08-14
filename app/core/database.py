"""Database connection and session management"""
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
from typing import Generator

from app.core.config import settings


# Create engine with appropriate settings based on database type
if settings.DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={"check_same_thread": False},  # SQLite specific
    )
else:
    engine = create_engine(
        settings.DATABASE_URL,
        pool_size=settings.DATABASE_POOL_SIZE,
        max_overflow=settings.DATABASE_MAX_OVERFLOW,
        pool_pre_ping=True,
    )

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def ensure_database_schema() -> None:
    """Apply small backward-compatible schema upgrades and remove obsolete tables."""
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TYPE workflowstatus ADD VALUE IF NOT EXISTS 'REJECTED'"
            ))

    inspector = inspect(engine)
    if "work_packages" not in inspector.get_table_names():
        return

    existing = {column["name"] for column in inspector.get_columns("work_packages")}
    statements = []
    if "ai_questions" not in existing:
        statements.append("ALTER TABLE work_packages ADD COLUMN ai_questions JSON")
    if "ai_question_responses" not in existing:
        statements.append("ALTER TABLE work_packages ADD COLUMN ai_question_responses JSON")
    if "tokens_used" not in existing:
        statements.append(
            "ALTER TABLE work_packages ADD COLUMN tokens_used INTEGER NOT NULL DEFAULT 0"
        )
    if "monthly_tokens_used" not in existing:
        statements.append(
            "ALTER TABLE work_packages ADD COLUMN monthly_tokens_used INTEGER NOT NULL DEFAULT 0"
        )
    if "token_usage_month" not in existing:
        statements.append(
            "ALTER TABLE work_packages ADD COLUMN token_usage_month VARCHAR(7)"
        )

    if statements:
        with engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    # Correct packages rejected before REJECTED became a distinct workflow state.
    with engine.begin() as connection:
        connection.execute(text("""
            UPDATE work_packages
            SET status = 'REJECTED'
            WHERE status = 'REWORK_REQUIRED'
              AND EXISTS (
                  SELECT 1 FROM reviews rejected_review
                  WHERE rejected_review.work_package_id = work_packages.id
                    AND rejected_review.decision = 'rejected'
                    AND NOT EXISTS (
                        SELECT 1 FROM reviews newer_review
                        WHERE newer_review.work_package_id = rejected_review.work_package_id
                          AND newer_review.started_at > rejected_review.started_at
                    )
              )
        """))

    # Audit now derives from reviews and execution_records. Parsed script steps
    # are held in the execution UI and recorded in execution_records.command_log.
    with engine.begin() as connection:
        connection.execute(text("DROP TABLE IF EXISTS audit_logs"))
        connection.execute(text("DROP TABLE IF EXISTS work_package_steps"))

    inspector = inspect(engine)
    if "reviews" in inspector.get_table_names():
        review_columns = {column["name"] for column in inspector.get_columns("reviews")}
        if "rollback_review_notes" not in review_columns:
            with engine.begin() as connection:
                connection.execute(text("ALTER TABLE reviews ADD COLUMN rollback_review_notes TEXT"))


def get_db() -> Generator:
    """Dependency for getting database sessions"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
