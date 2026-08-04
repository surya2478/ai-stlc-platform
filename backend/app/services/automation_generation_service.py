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
from app.services import locator_catalog
from app.services.project_application_service import (
    build_test_case_application_context,
    resolve_default_application,
    resolve_environment_url,
)


def _catalog_entry_page(entries: list[dict]) -> str | None:
    """The page a catalog describes, when it describes exactly one.

    `page_url` is written by the Studio planner onto the test case, so a test
    case that reached generation any other way carried none and left
    `_ground_entry_route` with nothing to ground against — the LLM's guessed
    entry path then survived into the script. Observed live on TC-0105
    (project 14): every element grounded cleanly against the published model,
    and the spec still opened `/#/`, which resolves against the application's
    base URL to the site root rather than to `/seleniumPractise/#/`, so the
    one element it needed was never on the page. The correct URL was sitting
    in the catalog the whole time.

    Only a unanimous page is returned. A catalog spanning several pages does
    not say which one a given test *enters* on, and picking the most common
    would be the same guesswork `_ground_entry_route` exists to prevent.
    """
    pages = {str(e["page"]).strip() for e in entries if e.get("page")}
    return pages.pop() if len(pages) == 1 else None


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
            catalog = await locator_catalog.build_for_application(
                db, project_id=project_id, application_id=application_id
            )
            payload.locator_map[application_id] = catalog.entries
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
            # (automation_agent._ground_entry_route). A test case that arrived
            # any other way has none, so the catalog answers instead when it
            # describes a single page: the elements this test will use were
            # observed there, which is the same claim `page_url` makes.
            "page_url": (
                (tc.metadata_ or {}).get("page_url")
                or _catalog_entry_page(payload.locator_map.get(application_id) or [])
            ),
            # Every page the planner explored for this application — grounds
            # multi-hop wait_for_url/url-assertion targets the same way the
            # element catalog grounds locators. Empty for regular TCs.
            "explored_page_paths": (tc.metadata_ or {}).get("explored_page_paths") or [],
            **app_context,
        })
    return payload
