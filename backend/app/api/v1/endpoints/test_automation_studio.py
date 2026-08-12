"""Test Automation Studio endpoints — /api/v1/lab/test-automation-studio/*.

Isolated namespace with the same 404-when-disabled pattern as
application_models.py / automation_suites.py: every route 404s when
TEST_AUTOMATION_STUDIO_ENABLED is off, so a deployment that has not adopted
the module behaves exactly as it did before it existed.

Two gates apply to every route:
  1. the module gate — enabled, and the caller's global role may reach it
  2. the usual project-scoped `tas.*` permission
"""
from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, Query, Response, UploadFile, status

from app.api.deps import CurrentUser, DBSession, require_permission
from app.config import get_settings
from app.models.agent import AgentRun
from app.models.test_automation_studio import TasIntakeBatch, TasRefinedTestCase, TasScriptAsset
from app.schemas.test_automation_studio import (
    SUPPORTED_FRAMEWORKS,
    AssessCoverageRequest,
    DocRole,
    IntakeDocumentAttach,
    BulkClassifyRequest,
    BulkClassifyResponse,
    BulkDecisionResponse,
    BulkDeleteRequest,
    BulkRequirementDecision,
    BulkTestCaseDecision,
    CoverageAssessmentOut,
    DeletionSummary,
    DerivedRequirementOut,
    DerivedRequirementUpdate,
    GenerateRefinedTestCasesRequest,
    GenerateScriptsRequest,
    IntakeBatchCreate,
    IntakeBatchOut,
    IntakeBatchUpdate,
    IntakeDocumentBulkAttach,
    RefinedTestCaseOut,
    RefinedTestCaseUpdate,
    ScriptAssetOut,
    ScriptAssetUpdate,
    ScriptDecision,
    SourceTestCaseOut,
    StudioJobOut,
    StudioJobStatusOut,
    StudioSummaryOut,
)
from app.services.rbac_service import (
    TAS_APPROVE_REQUIREMENT,
    TAS_APPROVE_TEST_CASE,
    TAS_ASSESS_COVERAGE,
    TAS_CLASSIFY,
    TAS_EDIT_SCRIPT,
    TAS_EXPORT,
    TAS_GENERATE_SCRIPT,
    TAS_INTAKE,
    TAS_REFINE_TEST_CASES,
    TAS_VIEW,
    can_access_test_automation_studio,
)
from app.services import agent_run_service, document_service
from app.worker.tasks.test_automation_studio_tasks import (
    tas_assess_coverage,
    tas_extract_test_cases,
    tas_generate_scripts,
    tas_generate_test_cases,
)
from app.services.test_automation_studio import (
    coverage_service,
    export_service,
    intake_service,
    refinement_service,
    script_lab_service,
)

router = APIRouter()


def _require_enabled(current_user) -> None:
    if not get_settings().test_automation_studio_enabled:
        raise HTTPException(
            status_code=404,
            detail="Test Automation Studio is disabled (TEST_AUTOMATION_STUDIO_ENABLED=false)",
        )
    if not can_access_test_automation_studio(current_user):
        # 404, not 403: a role that cannot see the module in its navigation
        # should not be able to confirm the module exists by probing it.
        raise HTTPException(status_code=404, detail="Not found")


async def _guard(permission: str, project_id: int, current_user, db) -> None:
    _require_enabled(current_user)
    await require_permission(permission, project_id, current_user, db)


async def _batch_for_user(batch_id: int, permission: str, current_user, db) -> TasIntakeBatch:
    _require_enabled(current_user)
    batch = await intake_service.get_batch_or_404(db, batch_id)
    await require_permission(permission, batch.project_id, current_user, db)
    return batch


async def _test_case_for_user(
    test_case_id: int, permission: str, current_user, db
) -> TasRefinedTestCase:
    _require_enabled(current_user)
    test_case = await refinement_service.get_test_case_or_404(db, test_case_id)
    await require_permission(permission, test_case.project_id, current_user, db)
    return test_case


async def _script_for_user(script_id: int, permission: str, current_user, db) -> TasScriptAsset:
    _require_enabled(current_user)
    asset = await script_lab_service.get_script_or_404(db, script_id)
    await require_permission(permission, asset.project_id, current_user, db)
    return asset


def _enqueue(task, run, db, *, args: tuple) -> str:
    """Hand a task to Celery and record its id on the run.

    A broker that refuses the job must not leave a "queued" run nobody will
    ever pick up — the caller would poll it forever — so the failure is
    recorded on the run and surfaced immediately.
    """
    try:
        async_result = task.delay(*args)
    except Exception as exc:  # noqa: BLE001 - broker failures are the point
        run.status = "failed"
        run.error_message = f"Could not queue the job: {exc}"
        run.progress_message = "Queue failed"
        db.add(run)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "The background worker queue is unavailable, so this job could not be started. "
                "Check that the worker and Redis are running."
            ),
        ) from exc
    run.celery_task_id = async_result.id
    run.progress_percent = 5
    run.progress_message = "Queued for worker"
    db.add(run)
    return async_result.id


def _script_out(asset: TasScriptAsset, test_case: TasRefinedTestCase | None) -> ScriptAssetOut:
    return ScriptAssetOut(
        **{
            **ScriptAssetOut.model_validate(asset).model_dump(),
            "test_case_display_id": getattr(test_case, "tc_display_id", None),
            "test_case_title": getattr(test_case, "title", None),
        }
    )


# ── Job status ───────────────────────────────────────────────────────────────

# Only runs this module starts are readable here. Without the filter this would
# be a way to read any project's agent runs while holding only `tas.view`.
STUDIO_AGENT_NAMES = frozenset(
    {"tas_coverage_assessment", "tas_test_case_refinement", "tas_script_generation"}
)
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled", "error", "timeout"})


@router.get("/jobs/{agent_run_id}", response_model=StudioJobStatusOut)
async def get_job_status(agent_run_id: int, db: DBSession, current_user: CurrentUser):
    """Progress of a queued studio job — what the three screens poll."""
    _require_enabled(current_user)
    run = await db.get(AgentRun, agent_run_id)
    if run is None or run.agent_name not in STUDIO_AGENT_NAMES:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    await require_permission(TAS_VIEW, run.project_id, current_user, db)
    return StudioJobStatusOut(
        agent_run_id=run.id,
        agent_name=run.agent_name,
        status=run.status,
        progress_percent=run.progress_percent or 0,
        progress_message=run.progress_message,
        error_message=run.error_message,
        output_data=run.output_data,
        created_at=run.created_at,
        updated_at=run.updated_at,
        finished=run.status in TERMINAL_RUN_STATUSES,
    )


# ── Studio summary ───────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/summary", response_model=StudioSummaryOut)
async def get_summary(project_id: int, db: DBSession, current_user: CurrentUser):
    await _guard(TAS_VIEW, project_id, current_user, db)
    return StudioSummaryOut(**await refinement_service.summary(db, project_id))


# ── Screen 1: Requirement Coverage Assessment ────────────────────────────────

@router.get("/projects/{project_id}/batches", response_model=list[IntakeBatchOut])
async def list_batches(project_id: int, db: DBSession, current_user: CurrentUser):
    await _guard(TAS_VIEW, project_id, current_user, db)
    batches = await intake_service.list_batches(db, project_id)
    return [IntakeBatchOut(**intake_service.serialize_batch(batch)) for batch in batches]


@router.post("/projects/{project_id}/batches", response_model=IntakeBatchOut, status_code=201)
async def create_batch(
    project_id: int, body: IntakeBatchCreate, db: DBSession, current_user: CurrentUser
):
    await _guard(TAS_INTAKE, project_id, current_user, db)
    batch = await intake_service.create_batch(
        db, project_id=project_id, body=body, user_id=current_user.id
    )
    return IntakeBatchOut(**intake_service.serialize_batch(batch))


@router.get("/batches/{batch_id}", response_model=IntakeBatchOut)
async def get_batch(batch_id: int, db: DBSession, current_user: CurrentUser):
    batch = await _batch_for_user(batch_id, TAS_VIEW, current_user, db)
    return IntakeBatchOut(**intake_service.serialize_batch(batch))


@router.patch("/batches/{batch_id}", response_model=IntakeBatchOut)
async def update_batch(
    batch_id: int, body: IntakeBatchUpdate, db: DBSession, current_user: CurrentUser
):
    batch = await _batch_for_user(batch_id, TAS_INTAKE, current_user, db)
    updated = await intake_service.update_batch(
        db, batch=batch, body=body, user_id=current_user.id
    )
    return IntakeBatchOut(**intake_service.serialize_batch(updated))


@router.delete("/batches/{batch_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_batch(batch_id: int, db: DBSession, current_user: CurrentUser):
    batch = await _batch_for_user(batch_id, TAS_INTAKE, current_user, db)
    await intake_service.delete_batch(db, batch)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/batches/{batch_id}/upload", response_model=IntakeBatchOut, status_code=201)
async def upload_document_to_batch(
    batch_id: int,
    db: DBSession,
    current_user: CurrentUser,
    doc_role: DocRole = Query("other"),
    file: UploadFile = File(...),
):
    """Upload one document straight into a batch.

    The studio needs its own upload route rather than reusing
    POST /api/v1/documents/upload, because that endpoint is gated on
    MANAGE_PROJECT — a permission Test_Automation_Users deliberately does not
    hold, since holding it would make the studio role a project administrator.
    Uploading an intake document is a studio action, so it is gated on
    `tas.intake` instead.

    Only the authorization differs: storage, size limits, MIME and magic-byte
    validation and text extraction all still run through document_service,
    exactly as they do for the platform's own upload.
    """
    batch = await _batch_for_user(batch_id, TAS_INTAKE, current_user, db)
    document = await document_service.upload_document(
        db=db, project_id=batch.project_id, user_id=current_user.id, file=file
    )
    updated = await intake_service.attach_documents(
        db,
        batch=batch,
        documents=[IntakeDocumentAttach(document_id=document.id, doc_role=doc_role)],
    )
    return IntakeBatchOut(**intake_service.serialize_batch(updated))


@router.post("/batches/{batch_id}/documents", response_model=IntakeBatchOut)
async def attach_documents(
    batch_id: int, body: IntakeDocumentBulkAttach, db: DBSession, current_user: CurrentUser
):
    """Attach documents already uploaded elsewhere in the platform."""
    batch = await _batch_for_user(batch_id, TAS_INTAKE, current_user, db)
    updated = await intake_service.attach_documents(db, batch=batch, documents=body.documents)
    return IntakeBatchOut(**intake_service.serialize_batch(updated))


@router.patch("/batches/{batch_id}/documents/{link_id}", response_model=IntakeBatchOut)
async def set_document_role(
    batch_id: int,
    link_id: int,
    db: DBSession,
    current_user: CurrentUser,
    doc_role: str = Query(..., pattern="^(brd|srd|test_cases|other)$"),
):
    batch = await _batch_for_user(batch_id, TAS_INTAKE, current_user, db)
    updated = await intake_service.set_document_role(
        db, batch=batch, link_id=link_id, doc_role=doc_role
    )
    return IntakeBatchOut(**intake_service.serialize_batch(updated))


@router.delete("/batches/{batch_id}/documents/{link_id}", response_model=IntakeBatchOut)
async def detach_document(
    batch_id: int, link_id: int, db: DBSession, current_user: CurrentUser
):
    batch = await _batch_for_user(batch_id, TAS_INTAKE, current_user, db)
    updated = await intake_service.detach_document(db, batch=batch, link_id=link_id)
    return IntakeBatchOut(**intake_service.serialize_batch(updated))


@router.post("/batches/{batch_id}/assess", response_model=StudioJobOut, status_code=202)
async def assess_coverage(
    batch_id: int, body: AssessCoverageRequest, db: DBSession, current_user: CurrentUser
):
    """Screen 1's "Assess Coverage for Automation".

    Returns 202 with an agent run id. The assessment reads every attached
    document through an LLM and takes minutes, which no HTTP hop between the
    browser and this process will hold open — so the work runs on the worker
    and the client polls /agent-runs/{id} for progress.
    """
    batch = await _batch_for_user(batch_id, TAS_ASSESS_COVERAGE, current_user, db)
    batch = await coverage_service.prepare_assessment(
        db, batch=batch, body=body, user_id=current_user.id
    )
    run = await agent_run_service.start_agent_run(
        db,
        project_id=batch.project_id,
        user_id=current_user.id,
        agent_name="tas_coverage_assessment",
        input_data={
            "batch_id": batch.id,
            "derive_gap_requirements": body.derive_gap_requirements,
        },
        status="pending",
        progress_percent=0,
        progress_message="Queued",
    )
    task_id = _enqueue(
        tas_assess_coverage,
        run,
        db,
        args=(run.id, batch.id, current_user.id, {"derive_gap_requirements": body.derive_gap_requirements}),
    )
    await db.commit()
    return StudioJobOut(
        agent_run_id=run.id, task_id=task_id, status="queued", message="Coverage assessment queued"
    )


@router.post("/batches/{batch_id}/extract-test-cases", response_model=StudioJobOut, status_code=202)
async def extract_test_cases(batch_id: int, db: DBSession, current_user: CurrentUser):
    """Read the uploaded test cases into rows, without assessing coverage.

    Coverage needs a BRD or SRD to measure against; reading a test case sheet
    does not. Keeping the two on one button meant a batch holding only existing
    test cases had no way into the studio at all, even though refining those in
    place is what this module is for.

    Same 202-and-poll contract as the assessment: it is an LLM pass per
    document.
    """
    batch = await _batch_for_user(batch_id, TAS_ASSESS_COVERAGE, current_user, db)
    _, test_case_docs = coverage_service.split_batch_documents(batch)
    coverage_service.validate_test_case_documents_ready(test_case_docs)
    run = await agent_run_service.start_agent_run(
        db,
        project_id=batch.project_id,
        user_id=current_user.id,
        agent_name="tas_coverage_assessment",
        input_data={"batch_id": batch.id, "mode": "extract_test_cases"},
        status="pending",
        progress_percent=0,
        progress_message="Queued",
    )
    task_id = _enqueue(
        tas_extract_test_cases, run, db, args=(run.id, batch.id, current_user.id)
    )
    await db.commit()
    return StudioJobOut(
        agent_run_id=run.id, task_id=task_id, status="queued", message="Test case extraction queued"
    )


@router.get("/batches/{batch_id}/assessment", response_model=CoverageAssessmentOut | None)
async def get_assessment(batch_id: int, db: DBSession, current_user: CurrentUser):
    batch = await _batch_for_user(batch_id, TAS_VIEW, current_user, db)
    assessment = await intake_service.latest_assessment(db, batch.id)
    return CoverageAssessmentOut.model_validate(assessment) if assessment else None


@router.get("/projects/{project_id}/requirements", response_model=list[DerivedRequirementOut])
async def list_requirements(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    batch_id: int | None = None,
    status_filter: list[str] | None = Query(default=None, alias="status"),
):
    await _guard(TAS_VIEW, project_id, current_user, db)
    rows = await coverage_service.list_requirements(
        db, project_id=project_id, batch_id=batch_id, statuses=status_filter
    )
    return [DerivedRequirementOut.model_validate(row) for row in rows]


@router.patch("/requirements/{requirement_id}", response_model=DerivedRequirementOut)
async def update_requirement(
    requirement_id: int,
    body: DerivedRequirementUpdate,
    db: DBSession,
    current_user: CurrentUser,
):
    _require_enabled(current_user)
    requirement = await coverage_service.get_requirement_or_404(db, requirement_id)
    await require_permission(TAS_ASSESS_COVERAGE, requirement.project_id, current_user, db)
    updated = await coverage_service.update_requirement(
        db,
        requirement=requirement,
        updates=body.model_dump(exclude_unset=True),
        user_id=current_user.id,
    )
    return DerivedRequirementOut.model_validate(updated)


@router.post(
    "/projects/{project_id}/requirements/decide", response_model=list[DerivedRequirementOut]
)
async def decide_requirements(
    project_id: int, body: BulkRequirementDecision, db: DBSession, current_user: CurrentUser
):
    """Screen 1's bulk approve/reject."""
    await _guard(TAS_APPROVE_REQUIREMENT, project_id, current_user, db)
    rows = await coverage_service.decide_requirements(
        db, project_id=project_id, body=body, user_id=current_user.id
    )
    return [DerivedRequirementOut.model_validate(row) for row in rows]


@router.post(
    "/projects/{project_id}/requirements/delete", response_model=DeletionSummary
)
async def delete_requirements(
    project_id: int, body: BulkDeleteRequest, db: DBSession, current_user: CurrentUser
):
    """Delete derived requirements — Screen 1's row and bulk delete.

    POST rather than DELETE for the same reason /decide is: it carries a body
    of ids, and one selection is one call.
    """
    await _guard(TAS_ASSESS_COVERAGE, project_id, current_user, db)
    return await coverage_service.delete_requirements(
        db, project_id=project_id, requirement_ids=body.ids
    )


@router.get("/projects/{project_id}/source-test-cases", response_model=list[SourceTestCaseOut])
async def list_source_test_cases(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    batch_id: int | None = None,
):
    """The test cases read off the uploaded test case documents.

    These are Screen 2's primary refinement source: selecting one refines it in
    place, keeping the ID and name the sheet gave it. Each row reports the
    requirements it was assessed as covering and whether it has been refined
    already, so the screen can show what selecting it will actually do.
    """
    await _guard(TAS_VIEW, project_id, current_user, db)
    rows = await coverage_service.list_source_test_cases(
        db, project_id=project_id, batch_id=batch_id
    )
    covers = await coverage_service.requirement_keys_by_source_test_case(
        db, batch_ids={row.batch_id for row in rows}
    )
    refined_by_source = {
        refined.source_uploaded_test_case_id: refined
        for refined in await refinement_service.list_test_cases(db, project_id=project_id)
        if refined.source_uploaded_test_case_id is not None
    }

    payload: list[SourceTestCaseOut] = []
    for row in rows:
        out = SourceTestCaseOut.model_validate(row)
        out.covers_requirement_ids = covers.get(row.id, [])
        refined = refined_by_source.get(row.id)
        if refined is not None:
            out.refined_test_case_id = refined.id
            out.refined_status = refined.status
        payload.append(out)
    return payload


@router.post(
    "/projects/{project_id}/source-test-cases/delete", response_model=DeletionSummary
)
async def delete_source_test_cases(
    project_id: int, body: BulkDeleteRequest, db: DBSession, current_user: CurrentUser
):
    """Delete test cases read off an uploaded document.

    Gated on `tas.intake`: these rows are intake evidence, produced and
    refreshed by the same extraction the upload owns.
    """
    await _guard(TAS_INTAKE, project_id, current_user, db)
    return await coverage_service.delete_source_test_cases(
        db, project_id=project_id, source_ids=body.ids
    )


# ── Screen 2: Automation TC Coverage Assessment ──────────────────────────────

@router.post(
    "/projects/{project_id}/test-cases/generate", response_model=StudioJobOut, status_code=202
)
async def generate_test_cases(
    project_id: int,
    body: GenerateRefinedTestCasesRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Queue refinement. Returns 202 with an agent run id to poll."""
    await _guard(TAS_REFINE_TEST_CASES, project_id, current_user, db)
    await refinement_service.validate_generation_request(db, project_id=project_id, body=body)
    run = await agent_run_service.start_agent_run(
        db,
        project_id=project_id,
        user_id=current_user.id,
        agent_name="tas_test_case_refinement",
        input_data=body.model_dump(mode="json"),
        status="pending",
        progress_percent=0,
        progress_message="Queued",
    )
    task_id = _enqueue(
        tas_generate_test_cases,
        run,
        db,
        args=(run.id, project_id, current_user.id, body.model_dump(mode="json")),
    )
    await db.commit()
    return StudioJobOut(
        agent_run_id=run.id, task_id=task_id, status="queued", message="Test case generation queued"
    )


@router.get("/projects/{project_id}/test-cases", response_model=list[RefinedTestCaseOut])
async def list_test_cases(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    batch_id: int | None = None,
    status_filter: list[str] | None = Query(default=None, alias="status"),
    classification: list[str] | None = Query(default=None),
):
    await _guard(TAS_VIEW, project_id, current_user, db)
    rows = await refinement_service.list_test_cases(
        db,
        project_id=project_id,
        batch_id=batch_id,
        statuses=status_filter,
        classifications=classification,
    )
    return [RefinedTestCaseOut.model_validate(row) for row in rows]


@router.get("/test-cases/{test_case_id}", response_model=RefinedTestCaseOut)
async def get_test_case(test_case_id: int, db: DBSession, current_user: CurrentUser):
    test_case = await _test_case_for_user(test_case_id, TAS_VIEW, current_user, db)
    return RefinedTestCaseOut.model_validate(test_case)


@router.patch("/test-cases/{test_case_id}", response_model=RefinedTestCaseOut)
async def update_test_case(
    test_case_id: int, body: RefinedTestCaseUpdate, db: DBSession, current_user: CurrentUser
):
    test_case = await _test_case_for_user(test_case_id, TAS_REFINE_TEST_CASES, current_user, db)
    updated = await refinement_service.update_test_case(
        db, test_case=test_case, body=body, user_id=current_user.id
    )
    return RefinedTestCaseOut.model_validate(updated)


@router.post("/projects/{project_id}/test-cases/classify", response_model=BulkClassifyResponse)
async def bulk_classify(
    project_id: int, body: BulkClassifyRequest, db: DBSession, current_user: CurrentUser
):
    """Bulk Automation/Manual classification, policy-driven by default."""
    await _guard(TAS_CLASSIFY, project_id, current_user, db)
    rows, policy_id, policy_version, unresolved = await refinement_service.bulk_classify(
        db, project_id=project_id, body=body, user_id=current_user.id
    )
    return BulkClassifyResponse(
        updated=[RefinedTestCaseOut.model_validate(row) for row in rows],
        policy_id=policy_id,
        policy_version=policy_version,
        unresolved=unresolved,
    )


@router.post("/projects/{project_id}/test-cases/decide", response_model=BulkDecisionResponse)
async def decide_test_cases(
    project_id: int, body: BulkTestCaseDecision, db: DBSession, current_user: CurrentUser
):
    await _guard(TAS_APPROVE_TEST_CASE, project_id, current_user, db)
    updated, blocked = await refinement_service.decide_test_cases(
        db, project_id=project_id, body=body, user_id=current_user.id
    )
    return BulkDecisionResponse(
        updated=[RefinedTestCaseOut.model_validate(row) for row in updated], blocked=blocked
    )


@router.post("/test-cases/{test_case_id}/reopen", response_model=RefinedTestCaseOut)
async def reopen_test_case(test_case_id: int, db: DBSession, current_user: CurrentUser):
    test_case = await _test_case_for_user(test_case_id, TAS_APPROVE_TEST_CASE, current_user, db)
    updated = await refinement_service.reopen_test_case(
        db, test_case=test_case, user_id=current_user.id
    )
    return RefinedTestCaseOut.model_validate(updated)


@router.post("/projects/{project_id}/test-cases/delete", response_model=DeletionSummary)
async def delete_test_cases(
    project_id: int, body: BulkDeleteRequest, db: DBSession, current_user: CurrentUser
):
    """Delete refined test cases — Screen 2's row and bulk delete.

    Gated on the permission that generates them: whoever can produce a refined
    test case can discard it. Approved ones are included; the studio's approval
    is a working gate on generating scripts, not a records-retention control,
    and the response reports how many approved rows went so the screen can say
    so.
    """
    await _guard(TAS_REFINE_TEST_CASES, project_id, current_user, db)
    return await refinement_service.delete_test_cases(
        db, project_id=project_id, test_case_ids=body.ids
    )


@router.get("/projects/{project_id}/test-cases/export")
async def export_test_cases(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    format: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    classification: str = Query("all", pattern="^(all|automation|manual)$"),
    batch_id: int | None = None,
):
    """Download refined test cases, Manual and Automation kept separate.

    `xlsx` returns one workbook with a sheet per classification; `csv` returns
    a single flat file for the requested classification, since CSV has no
    concept of sheets.
    """
    await _guard(TAS_EXPORT, project_id, current_user, db)
    rows = await refinement_service.list_test_cases(
        db,
        project_id=project_id,
        batch_id=batch_id,
        classifications=[classification] if classification != "all" else None,
    )

    # The download reproduces the uploaded spreadsheet's columns, so it needs
    # the rows each test case inherits from: the sheet it came off, the
    # platform test case it matched, and the requirement it closes.
    context = await export_service.build_context(db, rows)

    if format == "xlsx":
        payload = export_service.to_excel(rows, context)
        return Response(
            content=payload,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="tas-test-cases-project-{project_id}.xlsx"'
                )
            },
        )

    if classification == "all":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "CSV export must target one classification - request "
                "classification=automation or classification=manual, or use format=xlsx."
            ),
        )
    payload = export_service.to_csv(rows, context, automation=classification == "automation")
    return Response(
        content=payload,
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                f'attachment; filename="tas-{classification}-test-cases-project-{project_id}.csv"'
            )
        },
    )


# ── Screen 3: Automation Script Lab ──────────────────────────────────────────

@router.get("/frameworks")
async def list_frameworks(current_user: CurrentUser):
    _require_enabled(current_user)
    return {"frameworks": list(SUPPORTED_FRAMEWORKS)}


@router.post("/projects/{project_id}/scripts/generate", response_model=StudioJobOut, status_code=202)
async def generate_scripts(
    project_id: int, body: GenerateScriptsRequest, db: DBSession, current_user: CurrentUser
):
    """Queue script generation. Returns 202 with an agent run id to poll.

    One script is one LLM call, so a selection of ten runs for minutes. The
    worker reports "Generating 4 of 10 (TC-0019)" as it goes.
    """
    await _guard(TAS_GENERATE_SCRIPT, project_id, current_user, db)
    await script_lab_service.validate_generation_request(db, project_id=project_id, body=body)
    run = await agent_run_service.start_agent_run(
        db,
        project_id=project_id,
        user_id=current_user.id,
        agent_name="tas_script_generation",
        input_data=body.model_dump(mode="json"),
        status="pending",
        progress_percent=0,
        progress_message="Queued",
    )
    task_id = _enqueue(
        tas_generate_scripts,
        run,
        db,
        args=(run.id, project_id, current_user.id, body.model_dump(mode="json")),
    )
    await db.commit()
    return StudioJobOut(
        agent_run_id=run.id, task_id=task_id, status="queued", message="Script generation queued"
    )


@router.get("/projects/{project_id}/scripts", response_model=list[ScriptAssetOut])
async def list_scripts(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    framework: str | None = Query(default=None, pattern="^(playwright|katalon|appium)$"),
    test_case_id: int | None = None,
):
    await _guard(TAS_VIEW, project_id, current_user, db)
    pairs = await script_lab_service.list_scripts(
        db, project_id=project_id, framework=framework, test_case_id=test_case_id
    )
    return [_script_out(asset, test_case) for asset, test_case in pairs]


@router.get("/scripts/{script_id}", response_model=ScriptAssetOut)
async def get_script(script_id: int, db: DBSession, current_user: CurrentUser):
    asset = await _script_for_user(script_id, TAS_VIEW, current_user, db)
    test_case = await refinement_service.get_test_case_or_404(db, asset.refined_test_case_id)
    return _script_out(asset, test_case)


@router.patch("/scripts/{script_id}", response_model=ScriptAssetOut)
async def update_script(
    script_id: int, body: ScriptAssetUpdate, db: DBSession, current_user: CurrentUser
):
    asset = await _script_for_user(script_id, TAS_EDIT_SCRIPT, current_user, db)
    updated = await script_lab_service.update_script(
        db, asset=asset, body=body, user_id=current_user.id
    )
    test_case = await refinement_service.get_test_case_or_404(db, updated.refined_test_case_id)
    return _script_out(updated, test_case)


@router.post("/scripts/{script_id}/decide", response_model=ScriptAssetOut)
async def decide_script(
    script_id: int, body: ScriptDecision, db: DBSession, current_user: CurrentUser
):
    asset = await _script_for_user(script_id, TAS_EDIT_SCRIPT, current_user, db)
    updated = await script_lab_service.decide_script(
        db, asset=asset, decision=body.decision, user_id=current_user.id
    )
    test_case = await refinement_service.get_test_case_or_404(db, updated.refined_test_case_id)
    return _script_out(updated, test_case)


@router.post("/projects/{project_id}/scripts/delete", response_model=DeletionSummary)
async def delete_scripts(
    project_id: int, body: BulkDeleteRequest, db: DBSession, current_user: CurrentUser
):
    """Delete generated scripts — Screen 3's delete.

    Gated on the permission that generates them, matching the test case
    delete: the test case survives, so a deleted script can be generated
    again from the same source.
    """
    await _guard(TAS_GENERATE_SCRIPT, project_id, current_user, db)
    return await script_lab_service.delete_scripts(
        db, project_id=project_id, script_ids=body.ids
    )


@router.get("/scripts/{script_id}/download")
async def download_script(script_id: int, db: DBSession, current_user: CurrentUser):
    asset = await _script_for_user(script_id, TAS_EXPORT, current_user, db)
    test_case = await refinement_service.get_test_case_or_404(db, asset.refined_test_case_id)
    # A script with extra files (Katalon's object repository, Appium's
    # capabilities) is not usable as a single file, so it downloads as a zip
    # even when only one was requested.
    if asset.files:
        payload = script_lab_service.build_zip([(asset, test_case)])
        return Response(
            content=payload,
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="{asset.script_key}.zip"'
            },
        )
    return Response(
        content=asset.code,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{asset.script_key}"'},
    )


@router.get("/projects/{project_id}/scripts/download")
async def download_scripts(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    framework: str | None = Query(default=None, pattern="^(playwright|katalon|appium)$"),
):
    await _guard(TAS_EXPORT, project_id, current_user, db)
    pairs = await script_lab_service.list_scripts(
        db, project_id=project_id, framework=framework
    )
    if not pairs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No generated scripts to download"
        )
    payload = script_lab_service.build_zip(pairs)
    suffix = f"-{framework}" if framework else ""
    return Response(
        content=payload,
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="tas-scripts-project-{project_id}{suffix}.zip"'
            )
        },
    )
