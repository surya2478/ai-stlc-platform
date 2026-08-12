"""Screen 1's "Assess Coverage for Automation" action and its results."""
from __future__ import annotations

import re
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import delete as sql_delete
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.test_automation_studio.coverage_agent import CoverageAssessmentAgent
from app.models.test_automation_studio import (
    TasCoverageAssessment,
    TasDerivedRequirement,
    TasIntakeBatch,
    TasIntakeDocument,
    TasRefinedTestCase,
    TasSourceTestCase,
)
from app.models.test_case import TestCase
from app.schemas.test_automation_studio import (
    AssessCoverageRequest,
    BulkRequirementDecision,
    DeletionSummary,
)
from app.services import agent_run_service
from app.services.test_automation_studio import intake_service, sheet_import
from app.services.test_automation_studio.progress import ProgressCallback
from app.services.test_automation_studio.progress import report as _report

REQUIREMENT_DOC_ROLES = {"brd", "srd"}
TEST_CASE_DOC_ROLES = {"test_cases"}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _slugify(value: str, fallback: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", (value or "").strip()).strip("-").upper()
    return (cleaned[:40] or fallback)


async def _next_requirement_key(db: AsyncSession, batch_id: int, index: int) -> str:
    """Sequential, batch-scoped requirement key.

    Batch-scoped rather than project-scoped because the key is only ever shown
    and compared inside one assessment, and a project-wide sequence would make
    two concurrent assessments contend for the same counter.
    """
    return f"TAS-REQ-{batch_id:04d}-{index:03d}"


def parse_template_test_cases(test_case_docs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Read whichever test case documents already follow the platform template.

    Returns (parsed rows, documents left for the agent). A sheet in the
    template is read directly: exact, complete and free, where the agent pass
    costs a call per segment and returns only the handful of fields it asks
    for — losing Domain, Channel, Product and every execution column before the
    export could hand them back.
    """
    parsed: list[dict] = []
    remaining: list[dict] = []
    for doc in test_case_docs:
        filename = doc.get("filename") or ""
        path = doc.get("file_path")
        if not (path and sheet_import.can_parse(filename)):
            remaining.append(doc)
            continue
        try:
            with open(path, "rb") as handle:
                contents = handle.read()
        except OSError:
            # The row survives but the file does not. Falling back keeps the
            # document usable through its extracted text.
            remaining.append(doc)
            continue

        rows = sheet_import.parse_sheet(contents, filename)
        if not rows:
            remaining.append(doc)
            continue
        for row in rows:
            row["source_document_id"] = doc.get("document_id")
            row["source_document_name"] = filename
        parsed.extend(rows)
    return parsed, remaining


def split_batch_documents(batch: TasIntakeBatch) -> tuple[list[dict], list[dict]]:
    """Partition a batch's documents into requirement sources and existing TCs."""
    requirement_docs: list[dict] = []
    test_case_docs: list[dict] = []
    for link in batch.documents:
        doc = link.document
        payload = {
            "document_id": link.document_id,
            "filename": getattr(doc, "original_filename", None),
            "text": getattr(doc, "extracted_text", None) or "",
            # The stored original, so a sheet in the platform's template can be
            # read as the table it is rather than as flattened text.
            "file_path": getattr(doc, "file_path", None),
        }
        if link.doc_role in REQUIREMENT_DOC_ROLES:
            requirement_docs.append(payload)
        elif link.doc_role in TEST_CASE_DOC_ROLES:
            test_case_docs.append(payload)
    return requirement_docs, test_case_docs


def validate_documents_ready(requirement_docs: list[dict], test_case_docs: list[dict]) -> None:
    """Raise if the batch cannot be assessed. Called before anything is queued.

    Queueing a job that is certain to fail costs the user a round trip through
    the worker to learn something knowable at the click.
    """
    if not requirement_docs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This batch has no document tagged 'brd' or 'srd'. Coverage is assessed against "
                "requirements, so at least one requirement document is needed."
            ),
        )

    # Extraction runs on the worker after upload. Starting an assessment before
    # it finishes would read empty text and report "no requirements could be
    # extracted" — which reads as a bad document rather than as a job that has
    # not run yet, and sends the user off to re-check a file that is fine.
    pending = [
        doc["filename"] or f"document {doc['document_id']}"
        for doc in requirement_docs + test_case_docs
        if not (doc.get("text") or "").strip()
    ]
    if pending and not any((doc.get("text") or "").strip() for doc in requirement_docs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Text extraction has not finished for: "
                + ", ".join(pending)
                + ". Wait for the documents to finish processing and try again."
            ),
        )


def validate_test_case_documents_ready(test_case_docs: list[dict]) -> None:
    """Raise if the batch has nothing to extract test cases from.

    Deliberately not `validate_documents_ready`: that one gates the coverage
    assessment and demands a BRD or SRD, because coverage is measured against
    requirements. Extracting the test cases off a sheet needs no such thing,
    and requiring one shut out the "refine what we already have" case
    entirely.
    """
    if not test_case_docs:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "This batch has no document tagged 'test_cases'. Attach the test case sheet "
                "you want to refine and try again."
            ),
        )

    pending = [
        doc["filename"] or f"document {doc['document_id']}"
        for doc in test_case_docs
        if not (doc.get("text") or "").strip()
    ]
    if len(pending) == len(test_case_docs):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Text extraction has not finished for: "
                + ", ".join(pending)
                + ". Wait for the documents to finish processing and try again."
            ),
        )


async def execute_test_case_extraction(
    db: AsyncSession,
    *,
    run,
    batch_id: int,
    user_id: int,
    on_progress: ProgressCallback | None = None,
) -> list[TasSourceTestCase]:
    """Read the uploaded test cases into rows without assessing coverage.

    The other half of what `execute_assessment` used to do exclusively. A batch
    carrying only a test case sheet can now reach Screen 2: the test cases get
    their identity, keep their ID and name, and are refined with the sheet as
    the only context there is. No assessment is recorded, so the batch's
    coverage stays honestly unassessed rather than reporting a percentage
    computed against no requirements.
    """
    batch = await intake_service.get_batch_or_404(db, batch_id)
    _, test_case_docs = split_batch_documents(batch)
    validate_test_case_documents_ready(test_case_docs)

    await _report(on_progress, 20, f"Reading {len(test_case_docs)} test case document(s)")

    # Sheets already in the platform's template are read directly — exact, and
    # complete enough that the download can hand back the format that was
    # uploaded. Anything else goes to the agent.
    parsed, remaining = parse_template_test_cases(test_case_docs)
    extracted = list(parsed)
    result = None
    if remaining:
        agent = CoverageAssessmentAgent()
        result = await agent.extract_test_cases(test_case_documents=remaining)
        if not result.success and not extracted:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=result.error or "Test case extraction failed",
            )
        if result.success:
            extracted.extend(result.data.get("existing_test_cases", []))

    if not extracted:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No test cases could be read from the supplied document(s).",
        )

    await _report(on_progress, 75, "Saving test cases")
    synced = await sync_source_test_cases(
        db,
        batch=batch,
        # No assessment ran, so there is none to attribute these to. The column
        # is nullable precisely for this path.
        assessment_id=None,
        extracted=extracted,
        user_id=user_id,
    )

    for link in batch.documents:
        if link.doc_role in TEST_CASE_DOC_ROLES:
            link.extraction_status = "extracted"
            link.extracted_test_case_count = sum(
                1 for tc in extracted if tc.get("source_document_id") == link.document_id
            )
            db.add(link)

    await agent_run_service.complete_agent_run(
        db,
        run,
        # None when every document was read straight from its sheet — no model
        # was called, so there is no agent result to record.
        agent_result=result,
        output_data={
            "test_cases": len(synced),
            "batch_id": batch.id,
            "read_from_sheet": len(parsed),
            "read_by_agent": len(extracted) - len(parsed),
        },
    )
    await db.commit()
    for row in synced:
        await db.refresh(row)
    await _report(on_progress, 100, f"{len(synced)} test case(s) ready to refine")
    return synced


async def sync_source_test_cases(
    db: AsyncSession,
    *,
    batch: TasIntakeBatch,
    assessment_id: int | None,
    extracted: list[dict],
    user_id: int,
) -> list[TasSourceTestCase]:
    """Persist the test cases read off the uploaded sheet, one row each.

    Upsert rather than replace. A refined test case points at these rows, so
    deleting and recreating them on every re-assessment would null the link
    (`ondelete=SET NULL`) and silently strand work the user has already
    reviewed. Matching on the display ID is exactly right here: that ID is the
    test case's identity to the team who wrote the sheet.

    Rows for test cases that have since disappeared from the document are left
    alone. They are evidence of what an earlier assessment saw, and anything
    refined from them still needs its source.
    """
    if not extracted:
        return []

    existing_rows = list(
        (
            await db.execute(
                select(TasSourceTestCase).where(TasSourceTestCase.batch_id == batch.id)
            )
        )
        .scalars()
        .all()
    )
    by_display = {row.tc_display_id.strip().casefold(): row for row in existing_rows}

    # A display ID that also exists in the platform's own test cases means the
    # sheet and the platform are describing one test case. Recording the link
    # lets refinement prefer the platform row, which carries structured
    # preconditions and test data the sheet does not.
    platform_by_display = {
        str(tc_display or "").strip().casefold(): tc_id
        for tc_id, tc_display in (
            await db.execute(
                select(TestCase.id, TestCase.test_case_id).where(
                    TestCase.project_id == batch.project_id,
                    TestCase.is_deleted.is_(False),
                )
            )
        ).all()
        if tc_display
    }

    synced: list[TasSourceTestCase] = []
    seen: set[str] = set()
    for index, entry in enumerate(extracted, start=1):
        display_id = str(entry.get("test_case_id") or "").strip()
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        if not display_id:
            # A sheet row the agent could not find an ID on. It still needs a
            # stable key to be addressable, and one derived from the batch and
            # position is stable as long as the document is.
            display_id = f"{_slugify(title, 'TC')[:60]}-{index:03d}"
        key = display_id.casefold()
        if key in seen:
            # Two rows claiming one ID. The first wins; the unique constraint
            # would reject the second anyway, and failing the whole assessment
            # over a duplicated ID in a spreadsheet would be disproportionate.
            continue
        seen.add(key)

        steps = [str(step) for step in (entry.get("steps") or []) if str(step).strip()]
        row = by_display.get(key)
        if row is None:
            row = TasSourceTestCase(
                project_id=batch.project_id,
                batch_id=batch.id,
                tc_display_id=display_id,
                created_by=user_id,
            )
        # Only an assessment claims these rows. A standalone extraction passes
        # None, and must not wipe the attribution an earlier assessment set.
        if assessment_id is not None:
            row.assessment_id = assessment_id
        row.title = title[:500]
        row.summary = entry.get("summary")
        row.steps = steps
        row.source_document_id = entry.get("source_document_id")
        row.source_ref = entry.get("source_ref")
        # Only a sheet read through the template carries the rest of the
        # columns. An agent-read document has none, and writing an empty dict
        # over a row a template read had already filled would lose them.
        source_row = entry.get("source_row")
        if isinstance(source_row, dict) and source_row:
            row.source_row = source_row
        elif not row.source_row:
            row.source_row = {}
        row.matched_platform_test_case_id = platform_by_display.get(key)
        row.updated_by = user_id
        db.add(row)
        synced.append(row)

    return synced


async def prepare_assessment(
    db: AsyncSession,
    *,
    batch: TasIntakeBatch,
    body: AssessCoverageRequest,
    user_id: int,
) -> TasIntakeBatch:
    """Request-time half: apply the application settings and validate.

    Everything that can be judged without calling an LLM happens here, so the
    caller gets a 4xx immediately instead of a queued job that fails a minute
    later in a worker they cannot see.
    """
    if body.application_id is not None or body.application_url is not None:
        from app.schemas.test_automation_studio import IntakeBatchUpdate

        batch = await intake_service.update_batch(
            db,
            batch=batch,
            body=IntakeBatchUpdate(
                application_id=body.application_id,
                application_url=body.application_url,
                application_environment=body.application_environment,
            ),
            user_id=user_id,
        )

    requirement_docs, test_case_docs = split_batch_documents(batch)
    validate_documents_ready(requirement_docs, test_case_docs)
    return batch


async def execute_assessment(
    db: AsyncSession,
    *,
    run,
    batch_id: int,
    derive_gap_requirements: bool,
    user_id: int,
    on_progress: ProgressCallback | None = None,
) -> TasCoverageAssessment:
    """Worker-time half: the LLM passes and the persistence.

    Takes an already-created AgentRun rather than making one, so the run id the
    endpoint handed the client is the one that reports progress.
    """
    batch = await intake_service.get_batch_or_404(db, batch_id)
    requirement_docs, test_case_docs = split_batch_documents(batch)
    validate_documents_ready(requirement_docs, test_case_docs)

    previous_version = (
        await db.execute(
            select(func.max(TasCoverageAssessment.version)).where(
                TasCoverageAssessment.batch_id == batch.id
            )
        )
    ).scalar_one() or 0

    batch.status = "assessing"
    batch.status_error = None
    db.add(batch)
    await db.commit()

    await _report(
        on_progress,
        20,
        f"Reading {len(requirement_docs)} requirement document(s) "
        f"and {len(test_case_docs)} test case document(s)",
    )

    # Same rule as the standalone extraction: a test case sheet in the
    # platform's template is read as the table it is. Assessing used to send it
    # to the model regardless, which dropped rows without saying so — 3 of 15
    # on one upload — and lost every column but four.
    parsed_test_cases, remaining_test_case_docs = parse_template_test_cases(test_case_docs)

    agent = CoverageAssessmentAgent()
    result = await agent.run(
        requirement_documents=requirement_docs,
        test_case_documents=remaining_test_case_docs,
        derive_gap_requirements=derive_gap_requirements,
        preparsed_test_cases=parsed_test_cases,
    )

    if not result.success:
        batch.status = "failed"
        batch.status_error = result.error
        db.add(batch)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=result.error or "Coverage assessment failed",
        )

    await _report(on_progress, 75, "Saving requirements and coverage")

    data = result.data
    requirements = data.get("requirements", [])
    existing_cases = data.get("existing_test_cases", [])
    coverage_rows = data.get("coverage_rows", [])
    derived = data.get("derived_requirements", [])

    state_by_title = {
        str(row.get("requirement_title") or "").strip().lower(): row for row in coverage_rows
    }
    covered = sum(1 for row in coverage_rows if row.get("coverage_state") == "covered")
    partial = sum(1 for row in coverage_rows if row.get("coverage_state") == "partially_covered")
    uncovered = sum(1 for row in coverage_rows if row.get("coverage_state") == "uncovered")
    total = len(requirements)
    # Partial coverage counts as half. Counting it as covered would report a
    # gap-free project that still has untested criteria; counting it as
    # uncovered would erase real work already done.
    coverage_percent = int(round(((covered + partial * 0.5) / total) * 100)) if total else 0

    # Only one assessment per batch is "current" — the grid reads the current
    # one, and leaving two marked current would make which results appear
    # depend on row order.
    await db.execute(
        update(TasCoverageAssessment)
        .where(TasCoverageAssessment.batch_id == batch.id)
        .values(is_current=False)
    )

    assessment = TasCoverageAssessment(
        project_id=batch.project_id,
        batch_id=batch.id,
        version=previous_version + 1,
        is_current=True,
        status="completed",
        total_requirements=total,
        covered_requirements=covered,
        partially_covered_requirements=partial,
        uncovered_requirements=uncovered,
        existing_test_case_count=len(existing_cases),
        derived_requirement_count=len(derived),
        coverage_percent=coverage_percent,
        coverage_rows=coverage_rows,
        extracted_test_cases=existing_cases,
        gap_summary={
            "document_errors": data.get("document_errors", []),
            "requirement_documents": len(requirement_docs),
            "test_case_documents": len(test_case_docs),
            "derive_gap_requirements": derive_gap_requirements,
        },
        agent_run_id=run.id,
        created_by=user_id,
    )
    db.add(assessment)
    await db.flush()

    # The uploaded test cases become addressable rows here. Screen 2 refines
    # them in place — keeping the ID and name off the sheet — instead of
    # minting a new test case from the requirement they happen to cover.
    await sync_source_test_cases(
        db,
        batch=batch,
        assessment_id=assessment.id,
        extracted=existing_cases,
        user_id=user_id,
    )

    # A re-assessment replaces the previous proposal set. Requirements already
    # approved are kept: they may already have refined test cases hanging off
    # them, and silently deleting an approved requirement would orphan work
    # the user has explicitly signed off.
    await db.execute(
        TasDerivedRequirement.__table__.delete().where(
            TasDerivedRequirement.batch_id == batch.id,
            TasDerivedRequirement.status.in_(["draft", "pending_approval", "rejected"]),
        )
    )

    existing_keys = set(
        (
            await db.execute(
                select(TasDerivedRequirement.requirement_key).where(
                    TasDerivedRequirement.batch_id == batch.id
                )
            )
        )
        .scalars()
        .all()
    )

    persisted: list[TasDerivedRequirement] = []
    index = 0
    for req in requirements:
        title = str(req.get("title") or "").strip()
        if not title:
            continue
        row = state_by_title.get(title.lower(), {})
        index += 1
        key = await _next_requirement_key(db, batch.id, index)
        while key in existing_keys:
            index += 1
            key = await _next_requirement_key(db, batch.id, index)
        existing_keys.add(key)
        persisted.append(
            TasDerivedRequirement(
                project_id=batch.project_id,
                batch_id=batch.id,
                assessment_id=assessment.id,
                requirement_key=key,
                title=title[:500],
                summary=req.get("summary"),
                acceptance_criteria=req.get("acceptance_criteria") or [],
                business_rules=req.get("business_rules") or [],
                ui_pages=req.get("ui_pages") or [],
                apis=req.get("apis") or [],
                test_data_needs=req.get("test_data_needs") or [],
                origin="extracted",
                coverage_state=row.get("coverage_state") or "uncovered",
                gap_reason=row.get("gap_reason"),
                source_refs=[
                    ref
                    for ref in [req.get("source_ref"), req.get("source_document_name")]
                    if ref
                ],
                covering_test_case_refs=row.get("covering_test_case_ids") or [],
                automation_relevance=req.get("automation_relevance"),
                priority=str(req.get("priority") or "Medium"),
                status="pending_approval",
                created_by=user_id,
                updated_by=user_id,
            )
        )

    for req in derived:
        title = str(req.get("title") or "").strip()
        if not title:
            continue
        index += 1
        key = await _next_requirement_key(db, batch.id, index)
        while key in existing_keys:
            index += 1
            key = await _next_requirement_key(db, batch.id, index)
        existing_keys.add(key)
        persisted.append(
            TasDerivedRequirement(
                project_id=batch.project_id,
                batch_id=batch.id,
                assessment_id=assessment.id,
                requirement_key=key,
                title=title[:500],
                summary=req.get("summary"),
                acceptance_criteria=req.get("acceptance_criteria") or [],
                business_rules=req.get("business_rules") or [],
                ui_pages=req.get("ui_pages") or [],
                apis=req.get("apis") or [],
                test_data_needs=req.get("test_data_needs") or [],
                origin="derived",
                coverage_state="uncovered",
                gap_reason=req.get("gap_reason"),
                source_refs=[req.get("covers_requirement_title")] if req.get("covers_requirement_title") else [],
                covering_test_case_refs=[],
                automation_relevance=req.get("automation_relevance"),
                priority=str(req.get("priority") or "Medium"),
                status="pending_approval",
                created_by=user_id,
                updated_by=user_id,
            )
        )

    for row in persisted:
        db.add(row)

    for link in batch.documents:
        if link.doc_role in REQUIREMENT_DOC_ROLES:
            link.extraction_status = "extracted"
            link.extracted_requirement_count = sum(
                1 for req in requirements if req.get("source_document_id") == link.document_id
            )
        elif link.doc_role in TEST_CASE_DOC_ROLES:
            link.extraction_status = "extracted"
            link.extracted_test_case_count = sum(
                1 for tc in existing_cases if tc.get("source_document_id") == link.document_id
            )
        db.add(link)

    batch.status = "assessed"
    batch.status_error = None
    db.add(batch)

    await agent_run_service.complete_agent_run(
        db,
        run,
        agent_result=result,
        output_data={
            "assessment_id": assessment.id,
            "requirements": total,
            "derived": len(derived),
            "coverage_percent": coverage_percent,
        },
    )
    await db.commit()
    await db.refresh(assessment)
    await _report(on_progress, 100, "Assessment complete")

    return assessment


async def list_requirements(
    db: AsyncSession,
    *,
    batch_id: int | None = None,
    project_id: int | None = None,
    statuses: list[str] | None = None,
) -> list[TasDerivedRequirement]:
    query = select(TasDerivedRequirement)
    if batch_id is not None:
        query = query.where(TasDerivedRequirement.batch_id == batch_id)
    if project_id is not None:
        query = query.where(TasDerivedRequirement.project_id == project_id)
    if statuses:
        query = query.where(TasDerivedRequirement.status.in_(statuses))
    query = query.order_by(TasDerivedRequirement.origin.asc(), TasDerivedRequirement.id.asc())
    return list((await db.execute(query)).scalars().all())


async def list_source_test_cases(
    db: AsyncSession,
    *,
    project_id: int,
    batch_id: int | None = None,
) -> list[TasSourceTestCase]:
    """The test cases read off the uploaded sheets, newest batch order."""
    query = select(TasSourceTestCase).where(TasSourceTestCase.project_id == project_id)
    if batch_id is not None:
        query = query.where(TasSourceTestCase.batch_id == batch_id)
    query = query.order_by(TasSourceTestCase.batch_id.asc(), TasSourceTestCase.id.asc())
    return list((await db.execute(query)).scalars().all())


async def requirement_keys_by_source_test_case(
    db: AsyncSession, *, batch_ids: set[int]
) -> dict[int, list[int]]:
    """Map each source test case id to the requirement ids it covers.

    The assessment recorded the relationship the other way round — each
    requirement lists the test case IDs covering it — because that is how
    coverage is judged. Refinement needs it inverted: given a test case to
    refine, which requirements describe what it is supposed to prove.
    """
    if not batch_ids:
        return {}

    sources = list(
        (
            await db.execute(
                select(TasSourceTestCase).where(TasSourceTestCase.batch_id.in_(batch_ids))
            )
        )
        .scalars()
        .all()
    )
    requirements = list(
        (
            await db.execute(
                select(TasDerivedRequirement).where(TasDerivedRequirement.batch_id.in_(batch_ids))
            )
        )
        .scalars()
        .all()
    )

    by_display: dict[tuple[int, str], int] = {
        (row.batch_id, row.tc_display_id.strip().casefold()): row.id for row in sources
    }
    mapping: dict[int, list[int]] = {}
    for req in requirements:
        for ref in req.covering_test_case_refs or []:
            source_id = by_display.get((req.batch_id, str(ref).strip().casefold()))
            if source_id is not None:
                mapping.setdefault(source_id, []).append(req.id)
    return mapping


async def get_requirement_or_404(db: AsyncSession, requirement_id: int) -> TasDerivedRequirement:
    row = await db.get(TasDerivedRequirement, requirement_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Studio requirement not found")
    return row


async def update_requirement(
    db: AsyncSession, *, requirement: TasDerivedRequirement, updates: dict, user_id: int
) -> TasDerivedRequirement:
    if requirement.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An approved requirement cannot be edited. Reject it first if it needs to change.",
        )
    for field, value in updates.items():
        if value is not None:
            setattr(requirement, field, value)
    requirement.updated_by = user_id
    db.add(requirement)
    await db.commit()
    await db.refresh(requirement)
    return requirement


async def decide_requirements(
    db: AsyncSession, *, project_id: int, body: BulkRequirementDecision, user_id: int
) -> list[TasDerivedRequirement]:
    """Bulk approve/reject — Screen 1's "Bulk Approve"."""
    rows = list(
        (
            await db.execute(
                select(TasDerivedRequirement).where(
                    TasDerivedRequirement.id.in_(body.requirement_ids),
                    TasDerivedRequirement.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    found_ids = {row.id for row in rows}
    missing = [rid for rid in body.requirement_ids if rid not in found_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Requirements not found in this project: {missing}",
        )

    target = "approved" if body.decision == "approve" else "rejected"
    for row in rows:
        row.status = target
        row.decision_reason = body.reason
        row.approved_by = user_id if target == "approved" else None
        row.approved_at = _now() if target == "approved" else None
        row.updated_by = user_id
        db.add(row)
    await db.commit()
    for row in rows:
        await db.refresh(row)
    return rows


# ── Deleting generated artefacts ─────────────────────────────────────────────

async def delete_requirements(
    db: AsyncSession, *, project_id: int, requirement_ids: list[int]
) -> DeletionSummary:
    """Remove derived requirements the assessment produced.

    Any refined test case generated from one survives — the FK is ON DELETE
    SET NULL — because the test case is a separately approved artefact with
    its own delete. It does lose the link back to the requirement, so the
    count is reported and the screen warns before the delete: a later
    regeneration can no longer recognise it as the same test case and would
    mint a new ID.
    """
    rows = list(
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
    found_ids = {row.id for row in rows}
    not_found = [rid for rid in requirement_ids if rid not in found_ids]
    if not rows:
        return DeletionSummary(not_found=not_found)

    unlinked = (
        await db.execute(
            select(func.count(TasRefinedTestCase.id)).where(
                TasRefinedTestCase.derived_requirement_id.in_(found_ids)
            )
        )
    ).scalar_one() or 0
    approved_deleted = sum(1 for row in rows if row.status == "approved")

    await db.execute(
        sql_delete(TasDerivedRequirement)
        .where(TasDerivedRequirement.id.in_(found_ids))
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    return DeletionSummary(
        deleted=sorted(found_ids),
        not_found=not_found,
        test_cases_unlinked=unlinked,
        approved_deleted=approved_deleted,
    )


async def delete_source_test_cases(
    db: AsyncSession, *, project_id: int, source_ids: list[int]
) -> DeletionSummary:
    """Remove test cases read off an uploaded document.

    The refined version of one, if it has been refined, stays: it is the
    automation artefact the rest of the studio works from, and its ID and
    title are already copies rather than references. Deleting the source only
    removes the intake evidence, so re-extracting the same document brings it
    back.
    """
    rows = list(
        (
            await db.execute(
                select(TasSourceTestCase).where(
                    TasSourceTestCase.id.in_(source_ids),
                    TasSourceTestCase.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    found_ids = {row.id for row in rows}
    not_found = [sid for sid in source_ids if sid not in found_ids]
    if not rows:
        return DeletionSummary(not_found=not_found)

    unlinked = (
        await db.execute(
            select(func.count(TasRefinedTestCase.id)).where(
                TasRefinedTestCase.source_uploaded_test_case_id.in_(found_ids)
            )
        )
    ).scalar_one() or 0

    await db.execute(
        sql_delete(TasSourceTestCase)
        .where(TasSourceTestCase.id.in_(found_ids))
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    return DeletionSummary(
        deleted=sorted(found_ids),
        not_found=not_found,
        test_cases_unlinked=unlinked,
    )
