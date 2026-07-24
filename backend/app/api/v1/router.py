"""
Central router - all v1 endpoint groups are registered here.
"""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    health, projects, users, documents,
    requirements, test_plans, test_cases, test_suites,
    test_data, automation, execution, defects,
    reports, agents, settings, jira, traceability, llm, rag, assistant, resource_ops,
    applications, reviews, playwright_studio, mcp_connections, video,
    grounded_poc, automation_classification, discovery, taxonomy,
)

api_router = APIRouter()

api_router.include_router(health.router, prefix="/health", tags=["Health"])
api_router.include_router(users.router, prefix="/users", tags=["Users"])
api_router.include_router(projects.router, prefix="/projects", tags=["Projects"])
api_router.include_router(documents.router, prefix="/documents", tags=["Documents"])
api_router.include_router(requirements.router, prefix="/requirements", tags=["Requirements"])
api_router.include_router(test_plans.router, prefix="/test-plans", tags=["Test Plans"])
api_router.include_router(test_cases.router, prefix="/test-cases", tags=["Test Cases"])
api_router.include_router(test_suites.router, prefix="/test-suites", tags=["Test Suites"])
api_router.include_router(test_data.router, prefix="/test-data", tags=["Test Data"])
api_router.include_router(automation.router, prefix="/automation", tags=["Automation"])
api_router.include_router(execution.router, prefix="/execution", tags=["Execution"])
api_router.include_router(defects.router, prefix="/defects", tags=["Defects"])
api_router.include_router(jira.router, prefix="/jira", tags=["Jira"])
api_router.include_router(traceability.router, prefix="/traceability", tags=["Traceability"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(agents.router, prefix="/agent-runs", tags=["Agent Runs"])
api_router.include_router(agents.router, prefix="/agents", tags=["Agent Runs"])
api_router.include_router(settings.router, prefix="/settings", tags=["Settings"])
api_router.include_router(llm.router, tags=["LLM Settings"])
api_router.include_router(applications.router, tags=["Applications"])
api_router.include_router(rag.router, prefix="/rag", tags=["RAG"])
api_router.include_router(assistant.router, prefix="/assistant", tags=["Assistant"])
api_router.include_router(resource_ops.router, prefix="/resource-operations", tags=["Resource Operations"])
api_router.include_router(reviews.router, prefix="/reviews", tags=["Reviews"])
api_router.include_router(playwright_studio.router, prefix="/playwright-studio", tags=["Playwright AI Studio"])
api_router.include_router(mcp_connections.router, prefix="/mcp-connections", tags=["MCP Connections"])
api_router.include_router(video.router, prefix="/video", tags=["Video"])
api_router.include_router(taxonomy.router, prefix="/taxonomy", tags=["Taxonomy"])
# Grounded Automation PoC — isolated namespace; every route (except
# /status) 404s unless GROUNDED_AUTOMATION_ENABLED=true.
api_router.include_router(
    grounded_poc.router, prefix="/poc/grounded-automation", tags=["Grounded Automation PoC"]
)
# Test Automation Classification & Routing (P1-S3 extension) — isolated
# namespace; every route 404s unless AUTOMATION_CLASSIFICATION_ENABLED=true.
api_router.include_router(
    automation_classification.router, prefix="/automation-classifications", tags=["Automation Classification"]
)
# UI-015 Live Discovery Session (P1-S4 extension) — isolated namespace;
# every route 404s unless DISCOVERY_SESSIONS_ENABLED=true.
api_router.include_router(discovery.router, prefix="/discovery", tags=["Live Discovery Session"])

