"""Shared input-payload builder for the automation_script generation agent.

Extracted verbatim from the /automation/agent/generate-scripts endpoint
(trigger_automation_agent) so Playwright AI Studio's bulk "Approve Plan"
gate can enqueue generation waves through the exact same grounding logic —
application context, per-application locator_map catalog, approved-only
filtering — without duplicating it. The endpoint keeps its HTTP semantics
by inspecting the skip lists returned here.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services import locator_map_service
from app.services.project_application_service import (
    build_test_case_application_context,
    resolve_default_application,
    resolve_environment_url,
)


@dataclass
class GenerationPayload:
    test_cases: list[dict] = field(default_factory=list)
    locator_map: dict[int, list[dict]] = field(default_factory=dict)
    skipped_not_approved: list[int] = field(default_factory=list)
    skipped_wrong_project: list[int] = field(default_factory=list)


async def build_generation_payload(
    db: AsyncSession, *, project_id: int, test_case_ids: list[int]
) -> GenerationPayload:
    payload = GenerationPayload()
    for tc_id in test_case_ids:
        r = await db.execute(select(TestCase).where(TestCase.id == tc_id))
        tc = r.scalar_one_or_none()
        if not tc:
            continue
        if tc.project_id != project_id:
            payload.skipped_wrong_project.append(tc_id)
            continue
        if tc.status != "approved":
            payload.skipped_not_approved.append(tc_id)
            continue
        app_context = await build_test_case_application_context(db, tc)
        application = None
        if tc.application_id:
            application = await db.get(ProjectApplication, tc.application_id)
        if application is None:
            application = await resolve_default_application(db, project_id)
        application_id = application.id if application else None
        # Never wired through to generation before, despite CONTRACT_SYSTEM's
        # own grounding rules referencing "application_url" — page objects
        # got relative routes with no real base URL to scope the locator
        # catalog against (see locator_policy.filter_catalog_by_page).
        application_url = resolve_environment_url(application, tc.test_phase or "QA") if application else None
        if application_id is not None and application_id not in payload.locator_map:
            entries = await locator_map_service.list_for_application(
                db, project_id=project_id, application_id=application_id
            )
            payload.locator_map[application_id] = [
                {
                    "element_name": e.element_name,
                    "page": e.page,
                    "role": e.recommended_strategy,
                    "business_meaning": e.business_meaning,
                    "recommended_locator": e.recommended_locator,
                    "confidence_score": e.confidence_score,
                }
                for e in entries
            ]
        payload.test_cases.append({
            "id": tc.id,
            "test_case_id": tc.test_case_id,
            "title": tc.title,
            "preconditions": tc.preconditions,
            "steps": tc.steps,
            "expected_result": tc.expected_result,
            "bdd_scenario": tc.bdd_scenario,
            "test_type": tc.test_type,
            "priority": tc.priority,
            "application_id": application_id,
            "application_url": application_url,
            # Studio-planned TCs record the live page their elements were
            # captured on — generation grounds the entry route to it
            # (automation_agent._ground_entry_route). None for regular TCs.
            "page_url": (tc.metadata_ or {}).get("page_url"),
            # Every page the planner explored for this application — grounds
            # multi-hop wait_for_url/url-assertion targets the same way the
            # element catalog grounds locators. Empty for regular TCs.
            "explored_page_paths": (tc.metadata_ or {}).get("explored_page_paths") or [],
            **app_context,
        })
    return payload
