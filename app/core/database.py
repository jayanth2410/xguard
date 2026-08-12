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


def ensure_work_package_ai_columns() -> None:
    """Add backward-compatible application columns without losing data."""
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
