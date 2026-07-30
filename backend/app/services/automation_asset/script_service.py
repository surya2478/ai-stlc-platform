"""UI-021 Script Editor — compiling an IR and dry-running the result.

Two operations, both delegating to engines that already exist:

  compile  -> app.services.script_compiler (the ONLY renderer of code, ADR-001)
  dry run  -> app.services.automation_runner (a real subprocess, not a simulation)

Nothing here renders code and nothing here judges quality. The Static Quality
Gate's verdict is persisted on the script at compile time so UI-023 reads a
stored fact rather than recomputing one.

A compile always writes a NEW `AutomationScript` row linked by
`parent_script_id`. Per ADR-001's rollback guarantee, a script version is never
mutated in place — not by repair, not by regeneration, not here.
"""
from __future__ import annotations

import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.automation.generation_contract import AutomationGenerationContract
from app.models.automation_script import AutomationScript
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.test_case import TestCase
from app.services import static_quality_gate
from app.services.automation_asset import ir_service
from app.services.automation_runner.dispatcher import run_script_for_execution
from app.services.automation_runner.preflight import is_available
from app.services.automation_runner.workspace import (
    materialize_bundle,
    reset_workspace,
    write_playwright_config,
    write_pytest_config,
)
from app.services.automation_suite.errors import AutomationSuiteError
from app.services.project_application_service import (
    resolve_default_application,
    resolve_environment_url,
)
from app.services.script_compiler import compiler

DRY_RUN_TIMEOUT_SECONDS = 300

# ScriptType -> the framework string the runner dispatches on.
_FRAMEWORK_FOR_SCRIPT_TYPE = {
    "playwright-typescript": "playwright",
    "pytest-python": "pytest",
}


async def _resolve_contract(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> tuple[dict, int | None]:
    """The contract to compile, and the IR draft id it came from.

    Prefers the editable IR draft; falls back to the contract stored on the
    current script so an asset generated before the recorder existed can still
    be recompiled. Resolved identically in evidence.py and workspace_service.py.
    """
    draft = await ir_service.current_draft(db, member, suite)
    if draft is not None and draft.contract:
        return draft.contract, draft.id

    if member.resolved_script_id is not None:
        script = await db.get(AutomationScript, member.resolved_script_id)
        if script is not None and script.contract:
            return script.contract, None

    raise AutomationSuiteError(
        404,
        "NO_CONTRACT",
        "This asset has no Automation IR to compile. Record the test case in the "
        "Live Recorder first.",
    )


async def compile_asset(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
    *,
    actor_id: int,
) -> AutomationScript:
    """Compile the current IR into a new AutomationScript version."""
    payload, _draft_id = await _resolve_contract(db, member, suite)

    validation = ir_service.validate_contract(payload)
    if not validation["valid"]:
        raise AutomationSuiteError(
            422,
            "IR_VALIDATION_FAILED",
            "The behaviour does not validate, so it cannot be compiled: "
            + "; ".join(f"{e['field']}: {e['message']}" for e in validation["errors"][:3]),
        )

    contract = AutomationGenerationContract.model_validate(payload)
    try:
        bundle = compiler.compile_contract(contract)
    except compiler.UnsupportedContractVersionError as exc:
        raise AutomationSuiteError(422, "UNSUPPORTED_CONTRACT_VERSION", str(exc)) from exc

    previous = (
        await db.get(AutomationScript, member.resolved_script_id)
        if member.resolved_script_id is not None
        else None
    )

    script = AutomationScript(
        project_id=suite.project_id,
        test_case_id=member.test_case_id,
        created_by=actor_id,
        script_id=f"ASC-{uuid.uuid4().hex[:8].upper()}",
        framework=_FRAMEWORK_FOR_SCRIPT_TYPE.get(contract.script_type, "playwright"),
        file_path=bundle.entry_path,
        code=bundle.files[bundle.entry_path],
        compiled_files=bundle.files,
        contract=contract.model_dump(by_alias=True),
        setup_required=bundle.setup_required,
        execution_command=bundle.execution_command,
        # ADR-001 rollback guarantee: a new row every time, never a mutation.
        version=(previous.version + 1) if previous else 1,
        parent_script_id=previous.id if previous else None,
        status="generated",
        metadata_={
            "compiler_version": bundle.compiler_version,
            "suite_id": suite.id,
            "suite_test_case_id": member.id,
        },
    )

    # Run the code-level gate now and persist the verdict, so UI-023 renders a
    # stored fact. The optional syntax check needs a materialised workspace and
    # is deliberately left to the dry run, which has one.
    gate = static_quality_gate.run_static_quality_gate(script)
    script.static_gate_result = gate.as_dict()
    if gate.passed:
        script.status = "static_passed"

    db.add(script)
    await db.flush()

    # The member points at the version its evaluation resolved against.
    member.resolved_script_id = script.id
    member.resolved_framework = script.framework
    await db.flush()
    return script


async def _base_url(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> str | None:
    test_case = await db.get(TestCase, member.test_case_id)
    application = None
    if test_case is not None and test_case.application_id:
        from app.models.project_application import ProjectApplication

        application = await db.get(ProjectApplication, test_case.application_id)
    if application is None:
        application = await resolve_default_application(db, suite.project_id)
    if application is None:
        return None
    environment = member.resolved_environment or "QA"
    return resolve_environment_url(application, environment)


async def dry_run_asset(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
    *,
    actor_id: int,
) -> dict:
    """Execute the compiled script through the real runner.

    Writes an `ExecutionRun` plus one `ExecutionResult` per test, each carrying
    `metadata_.dry_run = True` and `metadata_.automation_script_id`. That exact
    shape is what `automation_confidence_service._dry_run_stability` and
    autonomy precondition 4 read — it is the wiring that turns a neutral 0.5
    "no history" default into real evidence.
    """
    if member.resolved_script_id is None:
        raise AutomationSuiteError(
            409, "NOT_COMPILED", "Compile this asset before running it."
        )
    script = await db.get(AutomationScript, member.resolved_script_id)
    if script is None:
        raise AutomationSuiteError(404, "SCRIPT_NOT_FOUND", "The compiled script is missing.")

    framework = (script.framework or "playwright").lower()
    available, detail = is_available(framework)
    if not available:
        # The runner's real reason, not a generic failure. On a host without
        # Node this is the honest answer, and the UI shows it verbatim.
        raise AutomationSuiteError(422, "RUNNER_UNAVAILABLE", detail)

    workspace: Path = reset_workspace(f"asset-{member.id}-{uuid.uuid4().hex[:8]}")
    compiled_files = script.compiled_files or {}

    if framework == "playwright":
        write_playwright_config(
            workspace,
            base_url=await _base_url(db, member, suite),
            test_dir="specs" if compiled_files else ".",
        )
    else:
        write_pytest_config(workspace)

    if compiled_files:
        materialize_bundle(workspace=workspace, compiled_files=compiled_files)
        script_file = script.file_path or next(iter(compiled_files))
    else:
        raise AutomationSuiteError(
            422,
            "NO_COMPILED_FILES",
            "This script has no compiled bundle. Recompile it before running.",
        )

    runner_result = await run_script_for_execution(
        framework=framework,
        workspace=workspace,
        script_file_name=script_file,
        execution_command=script.execution_command,
        environment=member.resolved_environment,
        timeout_seconds=DRY_RUN_TIMEOUT_SECONDS,
    )

    run = ExecutionRun(
        project_id=suite.project_id,
        created_by=actor_id,
        execution_id=f"DRY-{uuid.uuid4().hex[:8].upper()}",
        # `run_status` on a successful runner call is "completed", NOT "passed".
        # The pass/fail verdict lives on each PerTestResult. Reading run_status
        # as the verdict would mark every successful run as not-passed and
        # permanently starve autonomy precondition 4.
        status="completed" if runner_result.run_status == "completed" else "failed",
        suite_name=suite.name,
        # NOT NULL in the database even though the model annotates it nullable
        # (a real model/DB drift). Follows the existing vocabulary:
        # automation_local, automation_local_batch, repair_dry_run.
        source_type="asset_dry_run",
    )
    db.add(run)
    await db.flush()

    results: list[ExecutionResult] = []
    for per_test in runner_result.results:
        row = ExecutionResult(
            execution_run_id=run.id,
            test_case_id=member.test_case_id,
            project_id=suite.project_id,
            test_name=per_test.name,
            status=per_test.status,
            duration_ms=per_test.duration_ms,
            error_message=per_test.error_message,
            execution_mode="automation",
            screenshot_url=per_test.screenshot_path,
            video_url=per_test.video_path,
            log_url=runner_result.log_path,
            metadata_={
                "dry_run": True,
                "automation_script_id": script.id,
                "suite_test_case_id": member.id,
                "runner": runner_result.metadata.get("runner"),
                "exit_code": runner_result.metadata.get("exit_code"),
                "trace_path": per_test.trace_path,
            },
        )
        db.add(row)
        results.append(row)

    if not runner_result.results:
        # A run that produced no per-test results still gets one row, so "it ran
        # and reported nothing" is queryable rather than indistinguishable from
        # "it was never run".
        row = ExecutionResult(
            execution_run_id=run.id,
            test_case_id=member.test_case_id,
            project_id=suite.project_id,
            test_name=script.script_id,
            status="error",
            error_message=runner_result.error_message or "The runner returned no test results.",
            execution_mode="automation",
            log_url=runner_result.log_path,
            metadata_={
                "dry_run": True,
                "automation_script_id": script.id,
                "suite_test_case_id": member.id,
                "runner": runner_result.metadata.get("runner"),
            },
        )
        db.add(row)
        results.append(row)

    all_passed = bool(runner_result.results) and all(
        r.status == "pass" for r in runner_result.results
    )
    if all_passed and script.status in ("generated", "static_passed"):
        script.status = "dry_run_passed"

    # Now that a workspace exists, the gate's optional syntax check can actually
    # run — it is skipped, not failed, when npx is unavailable.
    gate = static_quality_gate.run_static_quality_gate(script, workspace=workspace)
    script.static_gate_result = gate.as_dict()

    await db.flush()

    return {
        "execution_run_id": run.id,
        "run_status": runner_result.run_status,
        "all_passed": all_passed,
        "duration_seconds": runner_result.duration_seconds,
        "error_message": runner_result.error_message,
        "log_path": runner_result.log_path,
        "runner": runner_result.metadata.get("runner"),
        "exit_code": runner_result.metadata.get("exit_code"),
        "results": [
            {
                "id": r.id,
                "test_name": r.test_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "screenshot_url": r.screenshot_url,
                "video_url": r.video_url,
                "trace_path": (r.metadata_ or {}).get("trace_path"),
            }
            for r in results
        ],
        "static_gate_result": gate.as_dict(),
    }


async def list_dry_runs(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    *,
    project_id: int,
    limit: int = 20,
) -> list[ExecutionResult]:
    """Dry-run history for this member, newest first.

    `metadata_` is JSONB with no index, so the scan is capped and filtered in
    Python — the same approach and the same cap
    `automation_confidence_service._dry_run_stability` uses, deliberately, so
    the history panel and the score dimension can never disagree about which
    runs count.
    """
    if member.resolved_script_id is None:
        return []
    rows = (
        await db.execute(
            select(ExecutionResult)
            .where(ExecutionResult.project_id == project_id)
            .order_by(ExecutionResult.id.desc())
            .limit(200)
        )
    ).scalars().all()
    return [
        r
        for r in rows
        if (r.metadata_ or {}).get("dry_run")
        and (r.metadata_ or {}).get("automation_script_id") == member.resolved_script_id
    ][:limit]
