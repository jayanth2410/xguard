"""FastAPI main application"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.core.config import settings
from app.api import api_router
from app.models.database import Base
from app.core.database import engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events"""
    # Startup: Create database tables
    Base.metadata.create_all(bind=engine)
    yield
    # Shutdown: cleanup if needed


app = FastAPI(
    title=settings.APP_NAME,
    version=settings.APP_VERSION,
    description="""
    ## Maker-Checker Enterprise Workflow Platform

    A comprehensive platform for managing IT changes with AI-assisted creation,
    human review, dynamic validation, and controlled execution.

    ### Key Features:
    - **AI Maker**: Intelligent agents that analyze requirements and generate implementations
    - **Human Checker**: Expert review and approval workflow
    - **Validation Agent**: Dynamic context-aware pre-execution validation
    - **Executor**: Controlled change execution with JIT verification and rollback

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
