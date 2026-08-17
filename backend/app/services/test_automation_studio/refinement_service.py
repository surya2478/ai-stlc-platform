"""Screen 2: refined test cases — generation, editing, classification, approval."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.test_automation_studio.refinement_agent import TestCaseRefinementAgent
from app.config import get_settings
from app.models.project_application import ProjectApplication
from app.models.test_automation_studio import (
    TasCoverageAssessment,
    TasDerivedRequirement,
    TasIntakeBatch,
    TasRefinedTestCase,
    TasScriptAsset,
    TasSourceTestCase,
)
from app.models.test_case import TestCase
from app.schemas.test_automation_studio import (
    BulkClassifyRequest,
    BulkTestCaseDecision,
    DeletionSummary,
    GenerateRefinedTestCasesRequest,
    RefinedTestCaseUpdate,
)
from app.services import agent_run_service
from app.services.project_application_service import resolve_environment_url
from app.services.test_automation_studio import classification as classifier
from app.services.test_automation_studio import coverage_service
from app.services.test_automation_studio import test_data_bridge
from app.services.test_automation_studio.progress import ProgressCallback
from app.services.test_automation_studio.progress import report as _report

logger = logging.getLogger(__name__)
settings = get_settings()


def _now() -> datetime:
    return datetime.now(timezone.utc)


DISPLAY_ID_PREFIX = "TC-"


def highest_display_id_sequence(values: list[str | None]) -> int:
    """Highest `TC-NNNN` number among the supplied IDs, or 0 if none match.

    Zero padding is not part of the comparison: a sheet written as `TC-01` and
    a studio ID written as `TC-0001` are the same number, and treating them as
    unrelated would let the studio mint `TC-0002` next to an existing `TC-02`.
    The unique constraint is on the string, so the two would coexist happily in
    the database while reading as duplicates on the grid.
    """
    highest = 0
    for value in values:
        if not value:
            continue
        trimmed = value.strip()
        if not trimmed.upper().startswith(DISPLAY_ID_PREFIX):
            continue
        tail = trimmed[len(DISPLAY_ID_PREFIX) :]
        if tail.isdigit():
            highest = max(highest, int(tail))
    return highest


def format_display_id(sequence: int) -> str:
    return f"{DISPLAY_ID_PREFIX}{sequence:04d}"


async def _display_id_allocator(db: AsyncSession, project_id: int):
    """Return a callable handing out the next free `TC-0001`-style ID.

    Requirement 2b: new test cases must use the same ID format as existing
    ones. The sequence is taken across BOTH the platform's `test_cases` table
    and the studio's own rows, so a studio-derived ID can never collide with
    an ID the platform already issued.

    The counter is held in memory and the max is read exactly once, because
    the session runs with autoflush=False (see app/database.py). Re-querying
    per row — which is what this used to do — never sees the rows added
    earlier in the same run, so every derived test case in a batch was handed
    the identical ID and the insert died on uq_tas_refined_tc_version.
    """
    platform_ids = list(
        (
            await db.execute(
                select(TestCase.test_case_id).where(TestCase.project_id == project_id)
            )
        )
        .scalars()
        .all()
    )
    studio_ids = list(
        (
            await db.execute(
                select(TasRefinedTestCase.tc_display_id).where(
                    TasRefinedTestCase.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    # Uploaded sheet IDs count too. A derived test case minted as `TC-0002`
    # while the sheet already has a `TC-02` gives the project two test cases
    # that read as the same one.
    uploaded_ids = list(
        (
            await db.execute(
                select(TasSourceTestCase.tc_display_id).where(
                    TasSourceTestCase.project_id == project_id
                )
            )
        )
        .scalars()
        .all()
    )
    counter = {
        "next": max(
            highest_display_id_sequence(platform_ids),
            highest_display_id_sequence(studio_ids),
            highest_display_id_sequence(uploaded_ids),
        )
        + 1
    }

    def allocate() -> str:
        value = format_display_id(counter["next"])
        counter["next"] += 1
        return value

    return allocate


async def _application_in_project(
    db: AsyncSession, *, project_id: int, application_id: int | None
) -> ProjectApplication | None:
    """Load an application by id, refusing one from another project.

    `application_id` arrives on the generation request body, and the name and
    environment URL it resolves to are written onto the refined test case,
    returned by the read model and included in the export — so a lookup by
    primary key alone would hand a member of one project the application
    inventory of every other. Screen 1 already resolves it this way
    (`intake_service._resolve_application`); Screen 2 has to match.
    """
    if application_id is None:
        return None
    return (
        await db.execute(
            select(ProjectApplication).where(
                ProjectApplication.id == application_id,
                ProjectApplication.project_id == project_id,
            )
        )
    ).scalar_one_or_none()


async def _require_application_in_project(
    db: AsyncSession, *, project_id: int, application_id: int | None
) -> ProjectApplication | None:
    application = await _application_in_project(
        db, project_id=project_id, application_id=application_id
    )
    if application_id is not None and application is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected application does not belong to this project",
        )
    return application


async def _resolve_application_url(
    db: AsyncSession,
    *,
    project_id: int,
    batch: TasIntakeBatch | None,
    application_id: int | None,
    environment: str,
) -> tuple[int | None, str | None, str | None]:
    """Resolve (application_id, url, application_name) for generation."""
    app_id = application_id or (batch.application_id if batch else None)
    application: ProjectApplication | None = None
    if app_id is not None:
        # A caller-supplied id is rejected outright when it is not this
        # project's; one inherited from the batch degrades to "no application"
        # the way it always has, since the batch may simply have been unlinked.
        application = (
            await _require_application_in_project(
                db, project_id=project_id, application_id=app_id
            )
            if application_id is not None
            else await _application_in_project(
                db, project_id=project_id, application_id=app_id
            )
        )
    url = resolve_environment_url(application, environment) if application else None
    # The batch-level URL is the value the user typed on Screen 1. It wins
    # only when the application has nothing configured for this environment,
    # so a properly configured project is never overridden by a one-off entry.
    if not url and batch is not None:
        url = batch.application_url
    return app_id, url, (application.name if application else None)


async def _existing_test_cases_for_requirements(
    db: AsyncSession, *, project_id: int, requirements: list[TasDerivedRequirement]
) -> dict[int, list[TestCase]]:
    """Match approved studio requirements back to real platform test cases.

    The link is the test case IDs the coverage assessment recorded as covering
    the requirement. Those IDs came out of the uploaded test case document, so
    they are matched against `test_cases.test_case_id` — the same display ID a
    user would read off the sheet.
    """
    wanted: set[str] = set()
    for req in requirements:
        for ref in req.covering_test_case_refs or []:
            token = str(ref).strip()
            if token:
                wanted.add(token.casefold())
    if not wanted:
        return {}

    rows = list(
        (
            await db.execute(
                select(TestCase).where(
                    TestCase.project_id == project_id,
                    TestCase.is_deleted.is_(False),
                )
            )
        )
        .scalars()
        .all()
    )
    by_display = {str(tc.test_case_id or "").strip().casefold(): tc for tc in rows}

    mapping: dict[int, list[TestCase]] = {}
    for req in requirements:
        matched: list[TestCase] = []
        for ref in req.covering_test_case_refs or []:
            tc = by_display.get(str(ref).strip().casefold())
            if tc is not None:
                matched.append(tc)
        if matched:
            mapping[req.id] = matched
    return mapping


async def _load_requirements(
    db: AsyncSession, *, project_id: int, requirement_ids: list[int]
) -> list[TasDerivedRequirement]:
    if not requirement_ids:
        return []
    return list(
        (
            await db.execute(
                select(TasDerivedRequirement).where(
                    TasDerivedRequirement.id.in_(requirement_ids),
                    TasDerivedRequirement.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )


async def _load_source_test_cases(
    db: AsyncSession, *, project_id: int, source_test_case_ids: list[int]
) -> list[TasSourceTestCase]:
    if not source_test_case_ids:
        return []
    return list(
        (
            await db.execute(
                select(TasSourceTestCase).where(
                    TasSourceTestCase.id.in_(source_test_case_ids),
                    TasSourceTestCase.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )


async def validate_generation_request(
    db: AsyncSession, *, project_id: int, body: GenerateRefinedTestCasesRequest
) -> None:
    """Request-time checks, so a doomed job is refused before it is queued."""
    await _require_application_in_project(
        db, project_id=project_id, application_id=body.application_id
    )

    requirements = await _load_requirements(
        db, project_id=project_id, requirement_ids=body.requirement_ids
    )
    sources = await _load_source_test_cases(
        db, project_id=project_id, source_test_case_ids=body.source_test_case_ids
    )

    if body.requirement_ids and not requirements:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested requirements were found in this project",
        )
    if body.source_test_case_ids and not sources:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested uploaded test cases were found in this project",
        )

    # Only requirements carry an approval gate. Approval there is a decision to
    # add scope the documents imply but nothing tests yet; refining a test case
    # that already exists adds no scope, so gating it on someone approving the
    # requirement it happens to cover would block work that is already agreed.
    unapproved = [req.requirement_key for req in requirements if req.status != "approved"]
    if unapproved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only approved requirements can be refined into test cases. "
                f"Not approved: {', '.join(unapproved)}"
            ),
        )

    selected = len(requirements) + len(sources)
    if selected > settings.tas_max_test_cases_per_run:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{selected} item(s) selected, over the "
                f"{settings.tas_max_test_cases_per_run} limit for one run."
            ),
        )


async def generate_refined_test_cases(
    db: AsyncSession,
    *,
    project_id: int,
    body: GenerateRefinedTestCasesRequest,
    user_id: int,
    run=None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[TasRefinedTestCase], list[dict], int | None]:
    requirements = await _load_requirements(
        db, project_id=project_id, requirement_ids=body.requirement_ids
    )
    sources = await _load_source_test_cases(
        db, project_id=project_id, source_test_case_ids=body.source_test_case_ids
    )
    if not requirements and not sources:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Nothing to refine: none of the requested items were found in this project",
        )

    unapproved = [req.requirement_key for req in requirements if req.status != "approved"]
    if unapproved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Only approved requirements can be refined into test cases. "
                f"Not approved: {', '.join(unapproved)}"
            ),
        )

    anchor_batch_id = requirements[0].batch_id if requirements else sources[0].batch_id
    batch = await db.get(TasIntakeBatch, anchor_batch_id)
    environment = body.application_environment or (batch.application_environment if batch else "qa")
    app_id, app_url, app_name = await _resolve_application_url(
        db,
        project_id=project_id,
        batch=batch,
        application_id=body.application_id,
        environment=environment,
    )

    existing_map = (
        await _existing_test_cases_for_requirements(
            db, project_id=project_id, requirements=requirements
        )
        if body.include_existing_test_cases
        else {}
    )

    current_rows = list(
        (
            await db.execute(
                select(TasRefinedTestCase).where(
                    TasRefinedTestCase.project_id == project_id,
                    TasRefinedTestCase.is_current.is_(True),
                )
            )
        )
        .scalars()
        .all()
    )
    already = {(row.derived_requirement_id, row.source_test_case_id) for row in current_rows}
    already_uploaded = {
        row.source_uploaded_test_case_id
        for row in current_rows
        if row.source_uploaded_test_case_id is not None
    }
    # The FK above is ON DELETE SET NULL, so a refined test case whose source
    # row was deleted no longer answers to it. Matching the display ID as well
    # keeps that row recognised: without it, re-extracting a document mints new
    # source ids, every one looks unrefined, and the run silently produces a
    # second refined test case for a behaviour that already has one.
    already_display_ids = {
        row.tc_display_id.strip().casefold() for row in current_rows if row.tc_display_id
    }

    items: list[dict] = []
    context: dict[str, dict] = {}
    skipped: list[dict] = []
    # One existing test case can cover several of the selected requirements.
    # Refining it once per requirement would produce v1 and v2 of the same test
    # case in a single run, differing only in which requirement they cite — so
    # it is refined once, against the first requirement that claims it.
    claimed_test_case_ids: set[int] = set()

    def _requirement_payload(req: TasDerivedRequirement) -> dict:
        return {
            "requirement_key": req.requirement_key,
            "title": req.title,
            "summary": req.summary,
            "acceptance_criteria": req.acceptance_criteria or [],
            "business_rules": req.business_rules or [],
            "ui_pages": req.ui_pages or [],
            "apis": req.apis or [],
            "test_data_needs": req.test_data_needs or [],
        }

    # ── Uploaded test cases ──────────────────────────────────────────────────
    # The anchor is the test case, not the requirement: it is refined in place
    # and keeps the ID and name off the sheet. The requirements it was assessed
    # as covering come along as context so the agent knows what the test case
    # is meant to prove, which is the whole role documents play here.
    requirement_ids_by_source = await coverage_service.requirement_keys_by_source_test_case(
        db, batch_ids={row.batch_id for row in sources}
    )
    context_requirements: dict[int, TasDerivedRequirement] = {}
    wanted_requirement_ids = {
        req_id for ids in requirement_ids_by_source.values() for req_id in ids
    }
    if wanted_requirement_ids:
        for req in (
            await db.execute(
                select(TasDerivedRequirement).where(
                    TasDerivedRequirement.id.in_(wanted_requirement_ids)
                )
            )
        ).scalars().all():
            context_requirements[req.id] = req

    platform_by_id: dict[int, TestCase] = {}
    wanted_platform_ids = {
        row.matched_platform_test_case_id
        for row in sources
        if row.matched_platform_test_case_id is not None
    }
    if wanted_platform_ids:
        for tc in (
            await db.execute(select(TestCase).where(TestCase.id.in_(wanted_platform_ids)))
        ).scalars().all():
            platform_by_id[tc.id] = tc

    for source in sources:
        if not body.regenerate and source.id in already_uploaded:
            skipped.append(
                {
                    "test_case_id": source.tc_display_id,
                    "reason": "Already refined - pass regenerate=true to rebuild it.",
                }
            )
            continue
        if not body.regenerate and source.tc_display_id.strip().casefold() in already_display_ids:
            skipped.append(
                {
                    "test_case_id": source.tc_display_id,
                    "reason": (
                        "A refined test case already carries this ID, though the source it was "
                        "refined from has since been deleted. Pass regenerate=true to rebuild it "
                        "as a new version rather than a second test case."
                    ),
                }
            )
            continue

        # When the same test case also exists in the platform's own table, that
        # row is the better source: it carries structured preconditions, test
        # data and priority the sheet never had. The ID and name are identical
        # either way, so nothing the user cares about changes.
        platform_tc = platform_by_id.get(source.matched_platform_test_case_id or -1)
        if platform_tc is not None:
            claimed_test_case_ids.add(platform_tc.id)
            existing_payload = {
                "test_case_id": platform_tc.test_case_id,
                "preconditions": platform_tc.preconditions or [],
                "steps": platform_tc.steps or [],
                "expected_result": platform_tc.expected_result,
                "test_data": platform_tc.test_data or {},
                "priority": platform_tc.priority,
                "test_type": platform_tc.test_type,
            }
        else:
            existing_payload = {
                "test_case_id": source.tc_display_id,
                "preconditions": [],
                # The sheet's steps are plain strings; the agent reads them as
                # the current behaviour to rewrite into automation-ready steps.
                "steps": source.steps or [],
                "expected_result": None,
                "test_data": {},
                "priority": None,
                "test_type": None,
            }

        covering = [
            context_requirements[req_id]
            for req_id in requirement_ids_by_source.get(source.id, [])
            if req_id in context_requirements
        ]
        primary_requirement = covering[0] if covering else None
        ref = f"src{source.id}"
        items.append(
            {
                "ref": ref,
                "mode": "refine",
                "title": source.title,
                "existing": existing_payload,
                "requirement": (
                    _requirement_payload(primary_requirement)
                    if primary_requirement is not None
                    else {
                        # No requirement was matched to this test case. The
                        # summary off the sheet is then all the intent there is,
                        # and sending an empty requirement would leave the agent
                        # rewriting steps with nothing to check them against.
                        "requirement_key": None,
                        "title": source.title,
                        "summary": source.summary,
                        "acceptance_criteria": [],
                        "business_rules": [],
                        "ui_pages": [],
                        "apis": [],
                        "test_data_needs": [],
                    }
                ),
                "additional_requirements": [
                    _requirement_payload(req) for req in covering[1:]
                ],
            }
        )
        context[ref] = {
            "requirement": primary_requirement,
            "test_case": platform_tc,
            "source": source,
        }

    # Which requirements the uploaded test cases queued above already speak for.
    requirement_ids_covered_by_selection = {
        req_id
        for entry in context.values()
        if entry.get("source") is not None
        for req_id in requirement_ids_by_source.get(entry["source"].id, [])
    }

    # ── Approved gap requirements ────────────────────────────────────────────
    for req in requirements:
        req_payload = _requirement_payload(req)

        for tc in existing_map.get(req.id, []):
            if tc.id in claimed_test_case_ids:
                continue
            if not body.regenerate and (req.id, tc.id) in already:
                skipped.append(
                    {
                        "requirement_key": req.requirement_key,
                        "test_case_id": tc.test_case_id,
                        "reason": "Already refined - pass regenerate=true to rebuild it.",
                    }
                )
                continue
            claimed_test_case_ids.add(tc.id)
            ref = f"req{req.id}-tc{tc.id}"
            items.append(
                {
                    "ref": ref,
                    "mode": "refine",
                    "title": tc.title,
                    "existing": {
                        "test_case_id": tc.test_case_id,
                        "preconditions": tc.preconditions or [],
                        "steps": tc.steps or [],
                        "expected_result": tc.expected_result,
                        "test_data": tc.test_data or {},
                        "priority": tc.priority,
                        "test_type": tc.test_type,
                    },
                    "requirement": req_payload,
                }
            )
            context[ref] = {"requirement": req, "test_case": tc}

        if not body.regenerate and (req.id, None) in already:
            skipped.append(
                {
                    "requirement_key": req.requirement_key,
                    "reason": "Already refined - pass regenerate=true to rebuild it.",
                }
            )
            continue

        # A requirement the assessment found covered already has its behaviour
        # exercised by the existing test cases refined above. Generating an
        # extra test case for it would duplicate coverage the project already
        # has, which is the opposite of what this screen is for.
        #
        # An uploaded test case selected in this same run counts as that
        # coverage. Without this, selecting `TC-01` and the requirement it
        # covers would yield both a refined `TC-01` and a brand new test case
        # for the same behaviour — the duplication this screen exists to avoid.
        if req.coverage_state == "covered" and (
            existing_map.get(req.id) or req.id in requirement_ids_covered_by_selection
        ):
            continue

        ref = f"req{req.id}-new"
        items.append(
            {
                "ref": ref,
                "mode": "create",
                "title": req.title,
                "existing": None,
                "requirement": req_payload,
            }
        )
        context[ref] = {"requirement": req, "test_case": None}

    if not items:
        return [], skipped, None

    if len(items) > settings.tas_max_test_cases_per_run:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This selection would refine {len(items)} test cases, over the "
                f"{settings.tas_max_test_cases_per_run} limit for one run. Select fewer requirements."
            ),
        )

    if run is None:
        # Direct call (a script or a test) rather than a worker dispatch. The
        # run still gets recorded, so the audit trail does not depend on which
        # path invoked the work.
        run = await agent_run_service.start_agent_run(
            db,
            project_id=project_id,
            user_id=user_id,
            agent_name="tas_test_case_refinement",
            input_data={
                "requirement_ids": [req.id for req in requirements],
                "source_test_case_ids": [row.id for row in sources],
                "item_count": len(items),
                "application_id": app_id,
            },
        )

    await _report(on_progress, 10, f"Refining {len(items)} test case(s)")

    async def _on_item(done: int, total: int, label: str) -> None:
        # Counts what has finished, not what is starting: the agent refines
        # several test cases at once, so there is no single "current" one. The
        # label names the test case this report is for, which is the one that
        # just completed rather than the one furthest along.
        #
        # 10..65, leaving room for the persistence phase that follows.
        await _report(
            on_progress,
            10 + int((done / max(total, 1)) * 55),
            f"Refined {done} of {total} test case(s)" + (f" - {label}" if label else ""),
        )

    agent = TestCaseRefinementAgent()
    result = await agent.run(
        items=items,
        application_url=app_url,
        application_name=app_name,
        on_item=_on_item,
    )

    if not result.success:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.error or "Test case refinement failed",
        )

    await _report(on_progress, 70, "Resolving test data and classifying")


    for failure in result.data.get("failures", []):
        entry = context.get(str(failure.get("ref")), {})
        req = entry.get("requirement")
        tc = entry.get("test_case")
        source = entry.get("source")
        skipped.append(
            {
                "requirement_key": getattr(req, "requirement_key", None),
                "test_case_id": (
                    getattr(tc, "test_case_id", None)
                    or getattr(source, "tc_display_id", None)
                ),
                "reason": failure.get("error"),
            }
        )

    policy = await classifier.effective_policy(db, project_id=project_id, application_id=app_id)
    allocate_display_id = await _display_id_allocator(db, project_id)
    created: list[TasRefinedTestCase] = []

    for row in result.data.get("refined", []):
        entry = context.get(str(row.get("source_ref")))
        if entry is None:
            # A refined test case that cannot be traced back to what was
            # requested. Dropping it silently would leave the run reporting a
            # success the grid does not show, with nothing anywhere saying an
            # item went missing — so it is reported as skipped instead.
            skipped.append(
                {
                    "test_case_id": row.get("test_case_id") or row.get("title"),
                    "reason": (
                        "The refinement agent returned a test case that does not match anything "
                        f"in this request (ref {row.get('source_ref')!r}). It was not saved."
                    ),
                }
            )
            continue
        req: TasDerivedRequirement | None = entry["requirement"]
        source_tc: TestCase | None = entry["test_case"]
        uploaded: TasSourceTestCase | None = entry.get("source")

        if source_tc is not None:
            # Requirement 2b, enforced at the boundary rather than trusted from
            # the model: the ID and the name are the source's, always.
            display_id_value = source_tc.test_case_id
            title = source_tc.title
            origin = "existing"
        elif uploaded is not None:
            # Same rule for a test case that only ever existed on a sheet. This
            # is the case the module previously had no path for, and losing the
            # ID and name here is exactly what that gap looked like.
            display_id_value = uploaded.tc_display_id
            title = uploaded.title
            origin = "imported"
        else:
            origin = "derived"
            title = str(row.get("title") or req.title)[:500]
            # Regenerating a derived test case must produce a new VERSION of the
            # same test case, not a new test case. Minting a fresh ID here would
            # leave the project with two IDs for one behaviour and break the
            # link from any script already generated against the old one.
            prior_derived = (
                await db.execute(
                    select(TasRefinedTestCase)
                    .where(
                        TasRefinedTestCase.project_id == project_id,
                        TasRefinedTestCase.derived_requirement_id == req.id,
                        TasRefinedTestCase.source_test_case_id.is_(None),
                    )
                    .order_by(TasRefinedTestCase.version.desc())
                    .limit(1)
                )
            ).scalars().first()
            display_id_value = (
                prior_derived.tc_display_id if prior_derived is not None else allocate_display_id()
            )

        version = 1
        previous = (
            await db.execute(
                select(TasRefinedTestCase)
                .where(
                    TasRefinedTestCase.project_id == project_id,
                    TasRefinedTestCase.tc_display_id == display_id_value,
                )
                .order_by(TasRefinedTestCase.version.desc())
                .limit(1)
            )
        ).scalars().first()
        if previous is not None:
            version = previous.version + 1
            previous.is_current = False
            db.add(previous)

        data_requirements = row.get("test_data_requirements") or []
        test_data_ids, annotated = await test_data_bridge.materialize(
            db,
            project_id=project_id,
            user_id=user_id,
            test_case_display_id=display_id_value,
            test_case_title=title,
            requirements=data_requirements,
            environment=environment,
        )
        required, data_status, auto_notes = test_data_bridge.summarize(annotated)

        refined = TasRefinedTestCase(
            project_id=project_id,
            # An uploaded test case that no requirement claimed still belongs to
            # the batch it was uploaded in, so the grid's batch filter keeps it.
            batch_id=(
                req.batch_id
                if req is not None
                else (uploaded.batch_id if uploaded is not None else None)
            ),
            derived_requirement_id=req.id if req is not None else None,
            source_test_case_id=source_tc.id if source_tc is not None else None,
            source_uploaded_test_case_id=uploaded.id if uploaded is not None else None,
            origin=origin,
            tc_display_id=display_id_value,
            title=title,
            objective=row.get("objective"),
            preconditions=row.get("preconditions") or [],
            steps=row.get("steps") or [],
            expected_result=row.get("expected_result"),
            bdd_scenario=row.get("bdd_scenario"),
            application_id=app_id,
            application_url=app_url,
            priority=str(row.get("priority") or "Medium"),
            test_type=row.get("test_type"),
            test_data_required=required,
            test_data_status=data_status,
            test_data_notes=row.get("test_data_notes") or auto_notes,
            test_data_requirements=annotated,
            test_data_ids=test_data_ids,
            status="draft",
            version=version,
            is_current=True,
            agent_run_id=run.id,
            metadata_={"automation_blockers": row.get("automation_blockers") or []},
            created_by=user_id,
            updated_by=user_id,
        )

        decision, reason, findings = classifier.classify(refined, policy)
        refined.classification = decision
        refined.classification_source = "policy"
        refined.classification_reason = reason
        refined.manual_only_reasons = findings

        db.add(refined)
        created.append(refined)

    await agent_run_service.complete_agent_run(
        db,
        run,
        agent_result=result,
        # The skipped entries themselves, not a count — the reason each was
        # skipped is what the user needs, and this is where the UI reads it.
        output_data={"generated": len(created), "skipped": skipped},
    )
    try:
        await db.commit()
    except IntegrityError as exc:
        # Two runs generating for the same project concurrently can still race
        # on a display ID. That is a retryable clash, not a server fault, so it
        # says so instead of surfacing as an opaque 500.
        await db.rollback()
        await agent_run_service.fail_agent_run(
            db, run.id, error_message=f"Test case ID collision: {exc}"
        )
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "A test case ID collided with one created by another generation run. "
                "Nothing was saved - run the generation again."
            ),
        ) from exc

    for row in created:
        await db.refresh(row)
    return created, skipped, run.id


async def list_test_cases(
    db: AsyncSession,
    *,
    project_id: int,
    batch_id: int | None = None,
    statuses: list[str] | None = None,
    classifications: list[str] | None = None,
    current_only: bool = True,
) -> list[TasRefinedTestCase]:
    query = select(TasRefinedTestCase).where(TasRefinedTestCase.project_id == project_id)
    if current_only:
        query = query.where(TasRefinedTestCase.is_current.is_(True))
    if batch_id is not None:
        query = query.where(TasRefinedTestCase.batch_id == batch_id)
    if statuses:
        query = query.where(TasRefinedTestCase.status.in_(statuses))
    if classifications:
        query = query.where(TasRefinedTestCase.classification.in_(classifications))
    query = query.order_by(TasRefinedTestCase.tc_display_id.asc(), TasRefinedTestCase.version.desc())
    return list((await db.execute(query)).scalars().all())


async def get_test_case_or_404(db: AsyncSession, test_case_id: int) -> TasRefinedTestCase:
    row = await db.get(TasRefinedTestCase, test_case_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Refined test case not found")
    return row


async def update_test_case(
    db: AsyncSession, *, test_case: TasRefinedTestCase, body: RefinedTestCaseUpdate, user_id: int
) -> TasRefinedTestCase:
    if test_case.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An approved test case cannot be edited. Reopen it first.",
        )

    updates = body.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(test_case, field, value)

    # Steps are renumbered rather than trusted: a user who deletes step 3 in
    # the editor leaves a gap, and the script generator emits one script step
    # per test case step in order, so a gap becomes a misnumbered script.
    if "steps" in updates and isinstance(test_case.steps, list):
        for index, step in enumerate(test_case.steps, start=1):
            if isinstance(step, dict):
                step["step_number"] = index

    # An explicit edit to the data fields is the user's answer to the
    # "test data required" prompt, so it is recorded as theirs.
    if "test_data_ids" in updates or "test_data_requirements" in updates:
        if not updates.get("test_data_status"):
            test_case.test_data_status = "user_provided"
            test_case.test_data_required = False

    test_case.edited_by_user = True
    test_case.updated_by = user_id
    db.add(test_case)
    await db.commit()
    await db.refresh(test_case)
    return test_case


async def bulk_classify(
    db: AsyncSession, *, project_id: int, body: BulkClassifyRequest, user_id: int
) -> tuple[list[TasRefinedTestCase], int | None, int | None, list[dict]]:
    rows = list(
        (
            await db.execute(
                select(TasRefinedTestCase).where(
                    TasRefinedTestCase.id.in_(body.test_case_ids),
                    TasRefinedTestCase.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested test cases were found in this project",
        )

    application_id = next((row.application_id for row in rows if row.application_id), None)
    policy = await classifier.effective_policy(
        db, project_id=project_id, application_id=application_id
    )
    unresolved: list[dict] = []
    if policy is None and body.classification is None:
        unresolved.append(
            {
                "code": "CLASSIFICATION_POLICY_NOT_FOUND",
                "message": (
                    "No published automation classification policy for this project - the built-in "
                    "default manual-only conditions were applied instead."
                ),
            }
        )

    for row in rows:
        if body.classification is not None:
            findings = classifier.manual_only_findings(row, policy)
            # An explicit override is honoured, but a caller marking something
            # "automation" that the policy says is manual-only needs to know:
            # the finding is kept on the row so the grid can flag the conflict
            # rather than the override erasing the evidence.
            row.classification = body.classification
            row.classification_source = "manual"
            row.classification_reason = body.reason or "Set manually."
            row.manual_only_reasons = findings
            if body.classification == "automation" and findings:
                unresolved.append(
                    {
                        "test_case_id": row.id,
                        "tc_display_id": row.tc_display_id,
                        "code": "OVERRIDES_MANUAL_ONLY_POLICY",
                        "message": (
                            "Marked for automation despite matching a manual-only policy condition: "
                            + ", ".join(str(f["label"]) for f in findings)
                        ),
                    }
                )
        else:
            decision, reason, findings = classifier.classify(row, policy)
            row.classification = decision
            row.classification_source = "policy"
            row.classification_reason = reason
            row.manual_only_reasons = findings

        row.updated_by = user_id
        db.add(row)

    await db.commit()
    for row in rows:
        await db.refresh(row)
    return (
        rows,
        policy.id if policy else None,
        policy.version if policy else None,
        unresolved,
    )


async def decide_test_cases(
    db: AsyncSession, *, project_id: int, body: BulkTestCaseDecision, user_id: int
) -> tuple[list[TasRefinedTestCase], list[dict]]:
    rows = list(
        (
            await db.execute(
                select(TasRefinedTestCase).where(
                    TasRefinedTestCase.id.in_(body.test_case_ids),
                    TasRefinedTestCase.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested test cases were found in this project",
        )

    target = "approved" if body.decision == "approve" else "rejected"
    updated: list[TasRefinedTestCase] = []
    blocked: list[dict] = []

    for row in rows:
        if target == "approved":
            # Requirement 4's teeth. Approving a test case whose data nobody
            # has provided would send it to Screen 3 to have a script
            # generated against values that do not exist.
            if row.test_data_required and row.test_data_status == "needs_user_action":
                blocked.append(
                    {
                        "test_case_id": row.id,
                        "tc_display_id": row.tc_display_id,
                        "code": "TEST_DATA_REQUIRED",
                        "message": row.test_data_notes
                        or "Test data must be provided in the Test Data module before approval.",
                    }
                )
                continue
            if row.classification == "undecided":
                blocked.append(
                    {
                        "test_case_id": row.id,
                        "tc_display_id": row.tc_display_id,
                        "code": "CLASSIFICATION_REQUIRED",
                        "message": "Classify this test case as Automation or Manual before approving it.",
                    }
                )
                continue

        row.status = target
        row.decision_reason = body.reason
        row.approved_by = user_id if target == "approved" else None
        row.approved_at = _now() if target == "approved" else None
        row.updated_by = user_id
        db.add(row)
        updated.append(row)

    await db.commit()
    for row in updated:
        await db.refresh(row)
    return updated, blocked


async def reopen_test_case(
    db: AsyncSession, *, test_case: TasRefinedTestCase, user_id: int
) -> TasRefinedTestCase:
    test_case.status = "draft"
    test_case.approved_by = None
    test_case.approved_at = None
    test_case.updated_by = user_id
    db.add(test_case)
    await db.commit()
    await db.refresh(test_case)
    return test_case


async def delete_test_cases(
    db: AsyncSession, *, project_id: int, test_case_ids: list[int]
) -> DeletionSummary:
    """Remove refined test cases and everything generated off them.

    Two things go beyond the rows named in the request, and both are
    deliberate:

    * every version sharing a `tc_display_id` goes, not just the current one.
      Versions are separate rows and only the current one is listed, so
      deleting that one alone would leave invisible history behind and the
      next generation run would resurrect the ID at version n+1.
    * scripts cascade at the database (`ondelete="CASCADE"`), because a script
      generated against a test case that no longer exists cannot be traced,
      regenerated or approved.

    Test data bound in the shared Test Data module is left alone: it is
    another module's data, and may be bound by test cases outside the studio.
    """
    named = list(
        (
            await db.execute(
                select(TasRefinedTestCase).where(
                    TasRefinedTestCase.id.in_(test_case_ids),
                    TasRefinedTestCase.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    found_ids = {row.id for row in named}
    not_found = [tc_id for tc_id in test_case_ids if tc_id not in found_ids]
    if not named:
        return DeletionSummary(not_found=not_found)

    display_ids = {row.tc_display_id for row in named}
    every_version = list(
        (
            await db.execute(
                select(TasRefinedTestCase).where(
                    TasRefinedTestCase.project_id == project_id,
                    TasRefinedTestCase.tc_display_id.in_(display_ids),
                )
            )
        )
        .scalars()
        .all()
    )
    doomed_ids = [row.id for row in every_version]
    approved_deleted = sum(1 for row in every_version if row.status == "approved")

    scripts_deleted = (
        await db.execute(
            select(func.count(TasScriptAsset.id)).where(
                TasScriptAsset.refined_test_case_id.in_(doomed_ids)
            )
        )
    ).scalar_one() or 0

    # A Core DELETE rather than db.delete(row): the ORM cascade would have to
    # lazy-load `scripts` for each row mid-flush, which raises under asyncio.
    # The FK is ON DELETE CASCADE, so the database removes them either way.
    await db.execute(
        sql_delete(TasRefinedTestCase)
        .where(TasRefinedTestCase.id.in_(doomed_ids))
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    return DeletionSummary(
        deleted=sorted(found_ids),
        not_found=not_found,
        versions_deleted=len(doomed_ids) - len(found_ids),
        scripts_deleted=scripts_deleted,
        approved_deleted=approved_deleted,
    )


async def summary(db: AsyncSession, project_id: int) -> dict:
    async def _count(model, *conditions) -> int:
        query = select(func.count(model.id)).where(model.project_id == project_id, *conditions)
        return (await db.execute(query)).scalar_one() or 0

    from app.models.test_automation_studio import TasScriptAsset

    current = TasRefinedTestCase.is_current.is_(True)
    by_framework_rows = (
        await db.execute(
            select(TasScriptAsset.framework, func.count(TasScriptAsset.id))
            .where(TasScriptAsset.project_id == project_id, TasScriptAsset.is_current.is_(True))
            .group_by(TasScriptAsset.framework)
        )
    ).all()

    return {
        "batches": await _count(TasIntakeBatch),
        "requirements_pending": await _count(
            TasDerivedRequirement, TasDerivedRequirement.status == "pending_approval"
        ),
        "requirements_approved": await _count(
            TasDerivedRequirement, TasDerivedRequirement.status == "approved"
        ),
        "test_cases_total": await _count(TasRefinedTestCase, current),
        "test_cases_pending": await _count(
            TasRefinedTestCase, current, TasRefinedTestCase.status.in_(["draft", "pending_approval"])
        ),
        "test_cases_approved": await _count(
            TasRefinedTestCase, current, TasRefinedTestCase.status == "approved"
        ),
        "test_cases_automation": await _count(
            TasRefinedTestCase, current, TasRefinedTestCase.classification == "automation"
        ),
        "test_cases_manual": await _count(
            TasRefinedTestCase, current, TasRefinedTestCase.classification == "manual"
        ),
        "test_cases_needing_test_data": await _count(
            TasRefinedTestCase,
            current,
            TasRefinedTestCase.test_data_required.is_(True),
            TasRefinedTestCase.test_data_status == "needs_user_action",
        ),
        "scripts_total": await _count(TasScriptAsset, TasScriptAsset.is_current.is_(True)),
        "scripts_by_framework": {framework: count for framework, count in by_framework_rows},
    }
