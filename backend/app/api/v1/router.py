"""
Central router - all v1 endpoint groups are registered here.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    health, projects, users, documents,
    requirements, test_plans,
    automation, execution, defects,
    reports, agents, settings,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(requirements.router, prefix="/requirements", tags=["Requirements"])
api_router.include_router(test_plans.router, prefix="/test-plans", tags=["Test Plans"])
api_router.include_router(automation.router, prefix="/automation", tags=["Automation"])
api_router.include_router(execution.router, prefix="/execution", tags=["Execution"])
api_router.include_router(defects.router, prefix="/defects", tags=["Defects"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(agents.router, prefix="/agent-runs", tags=["Agent Runs"])
api_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
