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

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_classification import AutomationClassificationPolicy
from app.services.test_classification.policy_defaults import (
    AUTOMATION_VALUE_WEIGHT_KEYS,
    CLASSIFICATION_CHECKS,
    COMPLEXITY_WEIGHT_KEYS,
)


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


def validate_policy_rules(rules: dict) -> None:
    conditions = rules.get("manual_only_conditions") or []
    if not isinstance(conditions, list) or len(conditions) > 50:
        raise ClassificationPolicyError(
            422, "CLASSIFICATION_POLICY_INVALID", "Manual-only conditions must be a list of at most 50 entries."
        )
    seen_codes: set[str] = set()
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ClassificationPolicyError(
                422, "CLASSIFICATION_POLICY_INVALID", "Each manual-only condition must be an object."
            )
        code = str(condition.get("code") or "").strip()
        label = str(condition.get("label") or "").strip()
        keywords = condition.get("keywords")
        if not code or not label or not isinstance(keywords, list) or not any(str(item).strip() for item in keywords):
            raise ClassificationPolicyError(
                422,
                "CLASSIFICATION_POLICY_INVALID",
                "Each manual-only condition requires a unique code, label, and at least one keyword.",
            )
        if code in seen_codes:
            raise ClassificationPolicyError(
                422, "CLASSIFICATION_POLICY_INVALID", f"Duplicate manual-only condition code '{code}'."
            )
        if len(code) > 80 or len(label) > 200 or any(len(str(item)) > 100 for item in keywords):
            raise ClassificationPolicyError(
                422, "CLASSIFICATION_POLICY_INVALID", "A manual-only condition exceeds the allowed length."
            )
        seen_codes.add(code)

    candidate = rules.get("candidate_rules") or {}
    block_if = set(candidate.get("block_if") or [])
    conditional_if = set(candidate.get("conditional_if") or [])
    unknown = (block_if | conditional_if) - set(CLASSIFICATION_CHECKS)
    if unknown:
        raise ClassificationPolicyError(
            422, "CLASSIFICATION_POLICY_INVALID", f"Unknown classification checks: {', '.join(sorted(unknown))}."
        )
    if block_if & conditional_if:
        raise ClassificationPolicyError(
            422, "CLASSIFICATION_POLICY_INVALID", "A criterion cannot be both blocking and conditional."
        )
    minimum = candidate.get("minimum_automation_value_score", 60)
    if not isinstance(minimum, (int, float)) or not 0 <= minimum <= 100:
        raise ClassificationPolicyError(
            422, "CLASSIFICATION_POLICY_INVALID", "Minimum automation-value score must be between 0 and 100."
        )

    weights = rules.get("scoring_weights") or {}
    for group, expected in (
        ("automation_value", AUTOMATION_VALUE_WEIGHT_KEYS),
        ("complexity", COMPLEXITY_WEIGHT_KEYS),
    ):
        configured = weights.get(group) or {}
        if set(configured) - expected:
            raise ClassificationPolicyError(
                422, "CLASSIFICATION_POLICY_INVALID", f"Unknown {group.replace('_', ' ')} scoring factor."
            )
        if any(not isinstance(value, (int, float)) or value < 0 or value > 100 for value in configured.values()):
            raise ClassificationPolicyError(
                422, "CLASSIFICATION_POLICY_INVALID", "Scoring weights must be between 0 and 100."
            )
        if configured and sum(configured.values()) <= 0:
            raise ClassificationPolicyError(
                422, "CLASSIFICATION_POLICY_INVALID", "Each scoring-weight group must have a positive total."
            )


async def publish_project_policy(
    db: AsyncSession,
    *,
    project_id: int,
    name: str,
    rules: dict,
    user_id: int,
) -> AutomationClassificationPolicy:
    validate_policy_rules(rules)
    latest = (
        await db.execute(
            select(AutomationClassificationPolicy)
            .where(
                AutomationClassificationPolicy.project_id == project_id,
                AutomationClassificationPolicy.application_id.is_(None),
            )
            .order_by(AutomationClassificationPolicy.version.desc())
            .limit(1)
        )
    ).scalars().first()
    now = datetime.now(timezone.utc)
    policy = AutomationClassificationPolicy(
        project_id=project_id,
        application_id=None,
        code=f"PROJECT_{project_id}_AUTOMATION",
        name=name.strip(),
        version=(latest.version + 1) if latest else 1,
        parent_policy_id=latest.id if latest else None,
        status="published",
        rules=rules,
        created_by=user_id,
        published_by=user_id,
        published_at=now,
    )
    db.add(policy)
    await db.flush()
    return policy


def require_published(policy: AutomationClassificationPolicy) -> None:
    if policy.status != "published":
        raise ClassificationPolicyError(
            status_code=409,
            code="CLASSIFICATION_POLICY_NOT_PUBLISHED",
            message=f"Policy '{policy.code}' v{policy.version} is not published.",
        )
