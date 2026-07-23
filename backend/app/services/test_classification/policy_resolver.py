"""Resolves the effective AutomationClassificationPolicy for a test case.

Scope precedence (most specific wins): application-scoped published policy
> project-scoped published policy > enterprise/global default (project_id
IS NULL). Mirrors the scope-matching shape used by
project_llm_settings_service.py for LLM route overrides — same "most
specific published row wins" idea, applied to a different domain.

v1 simplification: within a scope tier this picks the highest-`version`
published row. Multiple concurrently-published policies at the same exact
scope are not supported yet — publishing a new version at a scope
supersedes the previous one for resolution purposes (the old row stays in
history via `parent_policy_id`, it just stops being picked).
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_classification import AutomationClassificationPolicy


class ClassificationPolicyError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


async def _published_at_scope(
    db: AsyncSession, *, project_id: int | None, application_id: int | None
) -> AutomationClassificationPolicy | None:
    result = await db.execute(
        select(AutomationClassificationPolicy)
        .where(
            AutomationClassificationPolicy.status == "published",
            AutomationClassificationPolicy.project_id == project_id,
            AutomationClassificationPolicy.application_id == application_id,
        )
        .order_by(AutomationClassificationPolicy.version.desc())
        .limit(1)
    )
    return result.scalars().first()


async def resolve_effective_policy(
    db: AsyncSession, *, project_id: int, application_id: int | None = None
) -> AutomationClassificationPolicy:
    """Resolve the policy that applies to a test case in this project,
    optionally scoped to a specific application. Raises a structured 404 if
    no published policy exists at any tier — classification must never
    silently fall back to an implicit, unversioned default.
    """
    if application_id is not None:
        scoped = await _published_at_scope(db, project_id=project_id, application_id=application_id)
        if scoped is not None:
            return scoped

    project_scoped = await _published_at_scope(db, project_id=project_id, application_id=None)
    if project_scoped is not None:
        return project_scoped

    enterprise = await _published_at_scope(db, project_id=None, application_id=None)
    if enterprise is not None:
        return enterprise

    raise ClassificationPolicyError(
        status_code=404,
        code="CLASSIFICATION_POLICY_NOT_FOUND",
        message="No published automation classification policy is available for this project.",
    )


async def get_policy_or_404(db: AsyncSession, policy_id: int) -> AutomationClassificationPolicy:
    policy = await db.get(AutomationClassificationPolicy, policy_id)
    if policy is None:
        raise ClassificationPolicyError(
            status_code=404, code="CLASSIFICATION_POLICY_NOT_FOUND", message="Classification policy not found."
        )
    return policy


def require_published(policy: AutomationClassificationPolicy) -> None:
    if policy.status != "published":
        raise ClassificationPolicyError(
            status_code=409,
            code="CLASSIFICATION_POLICY_NOT_PUBLISHED",
            message=f"Policy '{policy.code}' v{policy.version} is not published.",
        )
