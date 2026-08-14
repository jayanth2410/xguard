"""FastAPI main application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.api import api_router
from app.models.database import Base
from app.core.database import engine, ensure_database_schema


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Create and upgrade application tables during startup."""
    Base.metadata.create_all(bind=engine)
    ensure_database_schema()
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## XGuard Enterprise Change Workflow

    Manage IT changes with AI-assisted preparation, human review, and
    controlled execution.

    ### Key Features:
    - **AI preparation**: Clarification questions, implementation, and rollback generation
    - **Human review**: Approval, rejection, and rework decisions
    - **Controlled execution**: SSH/WinRM execution with recorded results and rollback

    ### Change Types Supported:
    - Network (Firewall, Router, Switch)
    - Server (VM, OS, Patching)
    - Database (Schema, Config, Backup)
    - Cloud (AWS, Azure, GCP)
    - Application (Deploy, Config, Restart)
    - Security (IAM, Cert, Firewall Rule)
    - Container/K8s (Pods, Deploy, Scale)
    - Monitoring (Alerts, Dashboards)
    """,
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routes
app.include_router(api_router, prefix=settings.API_PREFIX)


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "status": "running",
        "docs": "/docs",
        "api": settings.API_PREFIX,
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy"}
