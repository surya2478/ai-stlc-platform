"""Automation Confidence Score (Phase 4.6b).

A composite 0-1 score per AutomationScript version, surfaced on approval
screens and dashboards alongside the staged lifecycle chain in
automation_service.advance_script_lifecycle. Every dimension here is a
best-effort read of facts the pipeline already computed elsewhere (locator
grounding confidence, the Static Quality Gate, dry-run history) — this
service does not re-derive or re-judge anything, it only aggregates.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult
from app.models.locator_map import LocatorMapEntry
from app.models.test_case import TestCase
from app.services.project_application_service import resolve_default_application, resolve_environment_url

# Equal weighting by default — no empirical basis yet to favor one dimension;
# revisit once enough real script history exists to correlate a dimension
# with actual production stability.
WEIGHTS = {
    "locator_confidence": 0.2,
    "assertion_confidence": 0.2,
    "data_readiness": 0.2,
    "environment_readiness": 0.2,
    "dry_run_stability": 0.2,
}

DRY_RUN_HISTORY_LIMIT = 10


def _locator_names_in_contract(contract: dict | None) -> set[str]:
    if not contract:
        return set()
    names = set()
    for page_object in contract.get("pageObjects", []) or []:
        for element in page_object.get("elements", []) or []:
            name = element.get("name")
            if name:
                names.add(name)
    return names


async def _locator_confidence(db: AsyncSession, script: AutomationScript) -> float:
    element_names = _locator_names_in_contract(script.contract)
    if not element_names:
        return 0.5  # no grounded elements referenced — neither credit nor penalize

    tc = await db.get(TestCase, script.test_case_id) if script.test_case_id else None
    application_id = tc.application_id if tc else None
    if application_id is None:
        return 0.5

    result = await db.execute(
        select(LocatorMapEntry).where(
            LocatorMapEntry.project_id == script.project_id,
            LocatorMapEntry.application_id == application_id,
            LocatorMapEntry.element_name.in_(element_names),
        )
    )
    entries = result.scalars().all()
    if not entries:
        return 0.5
    return sum(e.confidence_score for e in entries) / (100.0 * len(entries))


def _assertion_confidence(script: AutomationScript) -> float:
    gate = script.static_gate_result
    if not gate:
        return 0.5
    if not gate.get("passed", False):
        return 0.0
    violations = gate.get("violations") or []
    warnings = gate.get("warnings") or []
    score = 1.0 - 0.15 * len(violations) - 0.05 * len(warnings)
    return max(0.0, min(1.0, score))


async def _data_readiness(db: AsyncSession, script: AutomationScript) -> float:
    if not script.test_case_id:
        return 0.5
    tc = await db.get(TestCase, script.test_case_id)
    if tc is None:
        return 0.5
    return 1.0 if tc.test_data else 0.7


async def _environment_readiness(db: AsyncSession, script: AutomationScript) -> float:
    if not script.test_case_id:
        return 0.5
    tc = await db.get(TestCase, script.test_case_id)
    if tc is None:
        return 0.5
    from app.models.project_application import ProjectApplication
    application = await db.get(ProjectApplication, tc.application_id) if tc.application_id else None
    if application is None:
        application = await resolve_default_application(db, script.project_id)
    if application is None:
        return 0.0
    environment = tc.test_phase or "QA"
    url = resolve_environment_url(application, environment)
    return 1.0 if url else 0.5


async def _dry_run_stability(db: AsyncSession, script: AutomationScript) -> float:
    result = await db.execute(
        select(ExecutionResult)
        .where(ExecutionResult.project_id == script.project_id)
        .order_by(ExecutionResult.id.desc())
        .limit(200)  # cap the scan; filtered below by metadata since it isn't indexed
    )
    matches = [
        r for r in result.scalars().all()
        if (r.metadata_ or {}).get("automation_script_id") == script.id
        and (r.metadata_ or {}).get("dry_run")
    ][:DRY_RUN_HISTORY_LIMIT]
    if not matches:
        return 0.5  # no dry-run history yet — neutral, not penalized
    passed = sum(1 for r in matches if r.status == "pass")
    return passed / len(matches)


async def compute_confidence_score(db: AsyncSession, script: AutomationScript) -> dict:
    dimensions = {
        "locator_confidence": await _locator_confidence(db, script),
        "assertion_confidence": _assertion_confidence(script),
        "data_readiness": await _data_readiness(db, script),
        "environment_readiness": await _environment_readiness(db, script),
        "dry_run_stability": await _dry_run_stability(db, script),
    }
    overall = sum(dimensions[k] * WEIGHTS[k] for k in WEIGHTS)
    return {"overall": round(overall, 3), **{k: round(v, 3) for k, v in dimensions.items()}}
