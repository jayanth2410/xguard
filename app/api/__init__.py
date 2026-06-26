"""API routers"""
from fastapi import APIRouter
from app.api.v1 import work_packages, reviews, validation, execution, workflow, servicenow, ai

api_router = APIRouter()

api_router.include_router(work_packages.router, prefix="/work-packages", tags=["Work Packages"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(validation.router, prefix="/validation", tags=["Validation"])
api_router.include_router(execution.router, prefix="/execution", tags=["Execution"])
api_router.include_router(workflow.router, prefix="/workflow", tags=["Workflow"])
api_router.include_router(servicenow.router, prefix="/servicenow", tags=["ServiceNow"])
api_router.include_router(ai.router, prefix="/ai", tags=["AI Generation"])
