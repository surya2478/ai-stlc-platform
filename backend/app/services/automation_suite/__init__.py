"""UI-018 Automation Workspace — Automation Test Suite service package.

Read order: `inheritance` resolves everything from authoritative sources and is
the only module that queries for evaluation; `readiness`, `conflicts`, `gaps`
and `status` are pure functions over what it returns; `suite_service` is the
DB-facing layer; `dashboard` computes the landing page's metrics.
"""
from app.services.automation_suite.errors import AutomationSuiteError  # noqa: F401
