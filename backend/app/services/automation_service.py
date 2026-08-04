"""Automation Script service — CRUD operations."""
from collections import Counter
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.integrations.automation.framework_adapters import (
    assess_framework_fit,
    framework_language,
    suitability_assessment,
    supported_framework_catalog,
)
from app.integrations.automation.connector_factory import get_automation_connector
from app.integrations.automation.result_normalizer import normalize_status
from app.models.automation_mapping import AutomationTestMapping
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.test_case import TestCase
from app.models.test_suite import TestSuite
from app.schemas.automation import AutomationScriptUpdate, AutomationTestMappingCreate, AutomationTestMappingUpdate
from app.services import traceability_service
from app.services.display_id_service import display_id, temporary_id
from app.services.project_application_service import list_applications


async def list_scripts(
    db: AsyncSession,
    project_id: int,
    test_case_id: int | None = None,
    status: str | None = None,
) -> list[AutomationScript]:
    stmt = (
        select(AutomationScript)
        .where(AutomationScript.project_id == project_id)
        .order_by(AutomationScript.created_at.desc())
    )
    if test_case_id:
        stmt = stmt.where(AutomationScript.test_case_id == test_case_id)
    if status:
        stmt = stmt.where(AutomationScript.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_script(db: AsyncSession, script_id: int) -> AutomationScript | None:
    result = await db.execute(
        select(AutomationScript).where(AutomationScript.id == script_id)
    )
    return result.scalar_one_or_none()


async def update_script(
    db: AsyncSession, script: AutomationScript, updates: AutomationScriptUpdate
) -> AutomationScript:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(script, key, value)
    await db.flush()
    await db.refresh(script)
    return script


async def approve_script(
    db: AsyncSession, script: AutomationScript, action: str, notes: str | None
) -> AutomationScript:
    script.status = "approved" if action == "approve" else "rejected"
    if notes:
        metadata = {**(script.metadata_ or {}), "review_notes": notes}
        # Record WHAT was overridden, not just that a note was written. The
        # execution gate matches on this text, so an override only covers the
        # issue the approver actually saw — if the script changes and develops
        # a different problem, the old note no longer waves it through.
        if action == "approve" and (issue := _quality_issue_summary(script)):
            metadata["execution_override"] = {
                "issue": issue,
                "reason": notes,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        script.metadata_ = metadata
    await db.flush()
    await db.refresh(script)
    return script


def _regen_str(val) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val
    import json as _json
    return _json.dumps(val)


def _regen_str_list(val) -> list[str] | None:
    if val is None:
        return None
    if isinstance(val, list):
        return [_regen_str(item) for item in val]
    return [_regen_str(val)]


async def regenerate_script(db: AsyncSession, script: AutomationScript, user_id: int) -> AutomationScript:
    """Re-run script generation for an existing script's test case and
    overwrite its content in place, using current application/URL context
    (fixes scripts generated before an application was configured, e.g. ones
    that hardcoded a placeholder domain like example.com).

    Regeneration always resets status to "draft" regardless of prior status —
    previously-approved code has now changed and must be re-reviewed before it
    can run, matching the existing request_changes -> draft precedent.
    """
    from app.agents.automation.automation_agent import AutomationScriptAgent
    from app.models.project_application import ProjectApplication
    from app.services import locator_catalog
    from app.services.project_application_service import (
        build_test_case_application_context,
        resolve_default_application,
        resolve_environment_url,
    )

    if not script.test_case_id:
        raise HTTPException(status_code=422, detail="Script has no linked test case to regenerate from.")

    result = await db.execute(select(TestCase).where(TestCase.id == script.test_case_id))
    tc = result.scalar_one_or_none()
    if not tc:
        raise HTTPException(status_code=404, detail="Linked test case not found.")

    app_context = await build_test_case_application_context(db, tc)

    # Mirrors trigger_automation_agent's grounding lookup (automation.py) —
    # without this, regenerate silently fell back to ungrounded LLM guesses
    # even when Playwright MCP Discovery had already run for the test case's
    # application, since only the bulk generate-scripts endpoint fetched
    # locator_map before.
    application = None
    if tc.application_id:
        application = await db.get(ProjectApplication, tc.application_id)
    if application is None:
        application = await resolve_default_application(db, tc.project_id)
    locator_map: dict[str, list[dict]] = {}
    if application is not None:
        catalog = await locator_catalog.build_for_application(
            db, project_id=tc.project_id, application_id=application.id
        )
        locator_map[str(application.id)] = catalog.entries

    # Never wired through before, despite CONTRACT_SYSTEM's own grounding
    # rules referencing "application_url" — page objects got relative routes
    # with no real base URL to scope the locator catalog against (see
    # locator_policy.filter_catalog_by_page).
    application_url = resolve_environment_url(application, tc.test_phase or "QA") if application else None

    tc_dict = {
        "id": tc.id,
        "test_case_id": tc.test_case_id,
        "title": tc.title,
        "preconditions": tc.preconditions,
        "steps": tc.steps,
        "expected_result": tc.expected_result,
        "bdd_scenario": tc.bdd_scenario,
        "test_type": tc.test_type,
        "priority": tc.priority,
        "application_id": application.id if application else None,
        "application_url": application_url,
        **app_context,
    }

    agent = AutomationScriptAgent()
    agent_result = await agent.run(test_cases=[tc_dict], framework=script.framework, locator_map=locator_map)
    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Script regeneration failed")

    scripts_data = agent_result.data.get("scripts", [])
    if not scripts_data:
        agent_errors = [log["message"] for log in (agent_result.logs or []) if log.get("level") == "warning"]
        detail = "; ".join(agent_errors) if agent_errors else "LLM returned no parseable script"
        raise HTTPException(status_code=500, detail=f"Script regeneration produced nothing: {detail}")

    sc_data = scripts_data[0]
    script.file_path = _regen_str(sc_data.get("file_path")) or script.file_path
    script.code = _regen_str(sc_data.get("code")) or script.code
    script.setup_required = _regen_str_list(sc_data.get("setup_required")) or script.setup_required
    script.execution_command = _regen_str(sc_data.get("execution_command")) or script.execution_command
    script.compiled_files = sc_data.get("compiled_files") or script.compiled_files
    script.contract = sc_data.get("contract") or script.contract

    history = list((script.metadata_ or {}).get("transition_history", []))
    history.append({"action": "regenerate", "by": user_id, "from_status": script.status})
    script.metadata_ = {
        **(script.metadata_ or {}),
        "transition_history": history,
        # Was previously left stale from whatever generation attempt first
        # created this row — a regenerated script grounded in a live
        # locator_map catalog kept displaying "grounded: false" from before
        # Playwright MCP Discovery had ever run.
        "grounding": {
            "grounded": bool(sc_data.get("grounded", False)),
            "grounded_element_count": sc_data.get("grounded_element_count", 0),
            "ungrounded_elements": sc_data.get("ungrounded_elements", []),
        },
        "generation_attempts": sc_data.get("generation_attempts", []),
    }
    # A regenerated script has not been reviewed, so an approver's override of
    # the PREVIOUS version's issue must not carry over and wave it through.
    script.metadata_.pop("execution_override", None)
    script.status = "draft"

    # NOTE: this mutates the existing row in place rather than creating a new
    # version (see create_new_version / ADR-001's rollback guarantee). Phase
    # 4/5's bounded repair loop is the intended replacement for this call
    # path; tracked as a known gap until then, not silently unenforced.
    from app.services import static_quality_gate
    gate_result = static_quality_gate.run_static_quality_gate(script)
    script.static_gate_result = gate_result.as_dict()

    await db.flush()
    await db.refresh(script)
    return script


def _quality_issue_summary(script: AutomationScript) -> str | None:
    """The core "something is known to be wrong with this script" clause,
    shared by execution_blocked_reason (execution-time gate) and
    approval_override_reason (approval-time gate) — same positive-evidence
    signals, two different moments to catch them at. Callers append their
    own contextual suffix.
    """
    metadata = script.metadata_ or {}
    grounding = metadata.get("grounding") or {}
    ungrounded = grounding.get("ungrounded_elements") or []
    if ungrounded:
        shown = ", ".join(str(e) for e in ungrounded[:3])
        more = f" (+{len(ungrounded) - 3} more)" if len(ungrounded) > 3 else ""
        return f"{len(ungrounded)} element(s) not grounded to a real page ({shown}{more})"

    last_dry_run = metadata.get("last_dry_run") or {}
    if last_dry_run.get("passed") is False:
        return "the last dry run failed"

    return None


def execution_blocked_reason(script: AutomationScript) -> str | None:
    """Why this script can't be executed right now, or None if it can.

    "Approved" alone was the only gate the execute endpoints ever checked —
    but grounding and dry-run outcomes are known-good signals already stored
    on every script's metadata_ (see regenerate_script's "grounding" write
    and automation_tasks.py's "last_dry_run" write) that were never actually
    consulted. A script with unresolved locators or a known-failing dry run
    would show "approved" and run anyway, forever reproducing the same
    failure on every retry. Only blocks on *positive* evidence of a problem
    — a script with no grounding/dry-run metadata at all (e.g. externally
    authored, or predating this metadata) is treated as unknown, not bad.
    """
    if script.status == "needs_regeneration":
        return (
            "This script predates locator grounding fixes and is known to contain "
            "invalid locators — regenerate it before running."
        )
    if script.status not in {"approved", "executed"}:
        return "Script is not approved for execution yet."

    issue = _quality_issue_summary(script)
    if not issue:
        return None

    # An approver who acknowledged this exact issue in writing has already
    # taken responsibility for it — refusing anyway is a deadlock, not a
    # safeguard.
    #
    # Approval collects an audited override note (approval_override_reason)
    # and execution then ignored it, so the UI could truthfully say "an
    # override note is required", accept one, and still refuse. Some issues
    # cannot be regenerated away at all: an error banner that only exists
    # after a failed submit can never appear in a catalog crawled from the
    # form, so "regenerate before running" was advice that could not work.
    # Observed live 2026-08-03 on a login negative-path suite.
    #
    # Matched against the issue text recorded at approval, so an override
    # covers what was actually reviewed. Regeneration clears it (see
    # regenerate_script) — a fresh script has not been reviewed.
    override = (script.metadata_ or {}).get("execution_override") or {}
    if override.get("issue") == issue and (override.get("reason") or "").strip():
        return None

    return (
        f"{issue[0].upper()}{issue[1:]} — approve it with a note explaining why "
        "it should run anyway, or regenerate it."
    )


def approval_override_reason(script: AutomationScript, notes: str | None) -> str | None:
    """Why this approval needs an explicit override reason, or None if it
    can proceed as-is.

    A reviewer approving a script had no visibility into whether it had
    unresolved locators or had already failed its own dry run — "Approved"
    looked identical either way, and the underlying problem only surfaced
    later at execution time, forever reproducing the same failure. Rather
    than silently blocking approval outright (which would make regenerating
    the only path forward even when a reviewer has good reason to approve
    anyway — e.g. the dry run failed for an unrelated environment reason),
    approval is still allowed, but only with the reviewer's own notes as an
    explicit, audited acknowledgement of what they're overriding — the same
    notes already recorded via approval_service.create_approval_action.
    """
    if notes and notes.strip():
        return None
    issue = _quality_issue_summary(script)
    if not issue:
        return None
    return (
        f"This script has a known issue: {issue}. Approving it anyway requires a note "
        "explaining why — add one to the notes field and resubmit."
    )


# Allowed lifecycle transitions: source statuses that may move to (target, action label).
# Keep in sync with backend/app/models/automation_script.py status docs and
# frontend/src/components/automation/AutomationWorkspace.tsx action bar.
_TRANSITIONS: dict[str, dict[str, str]] = {
    "submit_for_review": {
        "ai_draft": "in_review",
        "draft": "in_review",
        # Phase 2: compiler-produced scripts that passed (or were left at
        # "generated" pending) the Static Quality Gate can go straight to review.
        "generated": "in_review",
        "static_passed": "in_review",
    },
    "request_changes": {
        "in_review": "draft",
        "pending_approval": "draft",
    },
    "restore_draft": {
        "rejected": "draft",
        "deprecated": "draft",
    },
}


async def transition_script(
    db: AsyncSession,
    script: AutomationScript,
    action: str,
    notes: str | None,
) -> AutomationScript:
    """Move an AutomationScript through its lifecycle state machine.

    Approve/reject still go through ``approve_script``. This helper covers
    submit-for-review, request-changes, and restore-from-rejected. Any other
    transition is rejected so the state machine stays narrow.
    """
    allowed = _TRANSITIONS.get(action)
    if allowed is None:
        raise ValueError(f"Unknown transition action: {action}")
    target = allowed.get(script.status)
    if target is None:
        raise ValueError(
            f"Cannot {action} a script in status '{script.status}'. "
            f"Allowed sources: {sorted(allowed)}"
        )
    script.status = target
    if notes:
        history = list((script.metadata_ or {}).get("transition_history", []))
        history.append({"action": action, "notes": notes, "to": target})
        script.metadata_ = {**(script.metadata_ or {}), "transition_history": history}
    await db.flush()
    await db.refresh(script)
    return script


async def create_new_version(
    db: AsyncSession,
    parent: AutomationScript,
    *,
    code: str,
    compiled_files: dict | None = None,
    contract: dict | None = None,
    status: str = "generated",
    file_path: str | None = None,
    execution_command: str | None = None,
) -> AutomationScript:
    """Create a new AutomationScript version superseding `parent` (Phase 2,
    ADR-001 rollback guarantee). The parent row is never mutated or
    deleted — only its status may later change (e.g. to "deprecated") once
    the caller has confirmed the new version is promoted; this helper does
    not do that itself, since "promoted" is a later-phase (repair loop /
    healing) decision, not a generic versioning concern.

    file_path/execution_command default to the parent's values, but callers
    that recompiled the contract (e.g. the repair loop) must pass the fresh
    values through explicitly — the compiler derives the spec file name from
    contract.business_flow, which a repair patch can reword, so blindly
    inheriting the parent's file_path can point execution_command at a file
    that was never written to disk under the new compiled_files.
    """
    child = AutomationScript(
        project_id=parent.project_id,
        test_case_id=parent.test_case_id,
        created_by=parent.created_by,
        script_id=temporary_id("AS"),
        framework=parent.framework,
        file_path=file_path or parent.file_path,
        code=code,
        setup_required=parent.setup_required,
        execution_command=execution_command or parent.execution_command,
        version=parent.version + 1,
        parent_script_id=parent.id,
        compiled_files=compiled_files,
        contract=contract,
        status=status,
        agent_run_id=parent.agent_run_id,
    )
    db.add(child)
    await db.flush()
    child.script_id = display_id("AS", child.id)
    await db.flush()
    return child


async def persist_repair_outcome(
    db: AsyncSession,
    *,
    project_id: int,
    triggered_by: int,
    agent_run_id: int | None,
    parent_script: AutomationScript,
    repair: dict,
) -> AutomationScript | None:
    """Persists a RepairLoopAgent outcome: one new AutomationScript VERSION
    per attempt (the parent row is never mutated or deleted, so every
    attempt — including the ones that still failed — stays inspectable and
    restorable), each with its own dry-run evidence tagged
    source_type="repair_dry_run".

    Shared by the automatic dry-run-chain repair loop
    (agent_tasks.py's automation_repair_loop persistence, which has an
    AgentRun to hang project_id/triggered_by/agent_run_id off of) and the
    on-demand "Repair script" trigger for real execution failures (which
    doesn't have one) — both need the exact same persisted shape, so this
    was pulled out from what used to be inline-only agent_tasks.py logic
    rather than duplicated.

    Returns the last persisted version, or None if every attempt failed
    before producing anything compilable (llm_patch_failed/compile_failed
    on attempt 1 — nothing to version).
    """
    current_parent = parent_script
    last_version: AutomationScript | None = None
    for attempt in repair.get("attempts", []):
        if "compiled_files" not in attempt:
            continue  # llm_patch_failed / compile_failed — nothing to version

        status = "generated"
        if attempt.get("static_gate_passed"):
            status = "static_passed"
        if attempt.get("dry_run_passed"):
            status = "dry_run_passed"

        new_version = await create_new_version(
            db, current_parent,
            code=attempt["compiled_files"].get(attempt["file_path"], ""),
            compiled_files=attempt["compiled_files"],
            contract=attempt["contract"],
            status=status,
            file_path=attempt["file_path"],
            execution_command=attempt.get("execution_command"),
        )
        new_version.static_gate_result = attempt.get("static_gate_result")
        new_version.metadata_ = {
            **(new_version.metadata_ or {}),
            "source": "repair_loop",
            "repair_attempt": attempt.get("attempt"),
        }
        await db.flush()

        dry_run_result = attempt.get("dry_run_result")
        if dry_run_result:
            dr_results = dry_run_result.get("results", [])
            exec_run = ExecutionRun(
                project_id=project_id,
                created_by=triggered_by,
                triggered_by=triggered_by,
                execution_id=temporary_id("ER"),
                environment="dry-run",
                execution_type="automation",
                source_type="repair_dry_run",
                status="completed" if dry_run_result.get("run_status") == "completed" else "failed",
                total_tests=len(dr_results),
                passed=sum(1 for r in dr_results if r.get("status") == "pass"),
                failed=sum(1 for r in dr_results if r.get("status") == "fail"),
                skipped=sum(1 for r in dr_results if r.get("status") == "skip"),
                agent_run_id=agent_run_id,
                metadata_={
                    "automation_script_id": new_version.id,
                    "dry_run": True,
                    "repair_attempt": attempt.get("attempt"),
                },
            )
            db.add(exec_run)
            await db.flush()
            exec_run.execution_id = display_id("ER", exec_run.id)
            for r in dr_results:
                db.add(ExecutionResult(
                    execution_run_id=exec_run.id,
                    test_case_id=new_version.test_case_id,
                    project_id=project_id,
                    test_name=r.get("name") or new_version.script_id,
                    status=r.get("status") or "error",
                    duration_ms=r.get("duration_ms"),
                    error_message=r.get("error_message"),
                    stack_trace=r.get("stack_trace"),
                    screenshot_path=r.get("screenshot_path"),
                    video_path=r.get("video_path"),
                    trace_path=r.get("trace_path"),
                    metadata_={
                        "automation_script_id": new_version.id,
                        "dry_run": True,
                        "console_logs": r.get("console_logs"),
                        "network_logs": r.get("network_logs"),
                    },
                ))
            await db.flush()

        current_parent = new_version
        last_version = new_version

    if last_version is not None and not repair.get("resolved"):
        last_version.metadata_ = {**(last_version.metadata_ or {}), "repair_loop_exhausted": True}
    elif last_version is None and repair.get("attempts"):
        # Every attempt failed before producing anything compilable (all
        # llm_patch_failed / compile_failed / url_not_grounded) — there's no
        # new version to attach the failure detail to, but the original
        # script must not look like self-heal was never attempted. Record
        # what was tried and why it didn't converge directly on the parent
        # row, since that's the only row left to attach it to.
        current_parent.metadata_ = {
            **(current_parent.metadata_ or {}),
            "repair_loop_exhausted": True,
            "repair_attempts": [
                {"attempt": a.get("attempt"), "outcome": a.get("outcome"), "detail": a.get("detail")}
                for a in repair.get("attempts", [])
            ],
        }
        await db.flush()

    return last_version


async def classify_and_repair(
    db: AsyncSession, *, execution_result: ExecutionResult, triggered_by: int
) -> dict:
    """On-demand repair for a real (non-dry-run) execution failure — the
    manual counterpart to the automatic dry-run chain (automation_dry_run
    -> failure_classification -> automation_repair_loop), which never runs
    for real Command Center executions (automation_tasks.run_automation_script
    has no chain wiring at all). Classifies the failure first if it hasn't
    been already — writing the same metadata_.failure_classification shape
    the automatic chain writes, so it's indistinguishable from either path
    afterward — then only attempts repair when the classification is
    repairable (locator_issue/timeout). Other classifications
    (data_issue/environment_issue/app_defect/api_issue) return the
    classification without attempting a fix the repair loop was never
    designed to make; the caller routes those elsewhere (test data,
    environment config, defect drafting).
    """
    from app.agents.automation.repair_agent import RepairLoopAgent
    from app.agents.execution.failure_classification_agent import (
        REPAIRABLE_CLASSIFICATIONS,
        classify_by_rules,
        classify_with_llm,
    )
    from app.models.project_application import ProjectApplication
    from app.services import locator_catalog
    from app.services.project_application_service import resolve_default_application, resolve_environment_url

    classification_info = (execution_result.metadata_ or {}).get("failure_classification")
    if not classification_info:
        result_dict = {
            "error_message": execution_result.error_message,
            "stack_trace": execution_result.stack_trace,
            "network_logs": (execution_result.metadata_ or {}).get("network_logs"),
        }
        classification = classify_by_rules(result_dict)
        if classification:
            source, reason = "rules", f"Matched a deterministic rule for {classification}."
        else:
            classification, reason = await classify_with_llm(result_dict)
            source = "llm"
        classification_info = {
            "classification": classification,
            "reason": reason,
            "source": source,
            "repairable": classification in REPAIRABLE_CLASSIFICATIONS,
        }
        execution_result.metadata_ = {
            **(execution_result.metadata_ or {}),
            "failure_classification": classification_info,
        }
        await db.flush()

    outcome: dict = {
        "classification": classification_info.get("classification"),
        "classification_reason": classification_info.get("reason"),
        "repairable": bool(classification_info.get("repairable")),
        "repaired": False,
        "new_script_id": None,
        "attempts": [],
        "error": None,
    }
    if not outcome["repairable"]:
        return outcome

    automation_script_id = (execution_result.metadata_ or {}).get("automation_script_id")
    if not automation_script_id:
        outcome["error"] = "No linked automation script to repair."
        return outcome
    script = await db.get(AutomationScript, automation_script_id)
    if not script or not script.contract:
        outcome["error"] = "Linked script has no contract to repair from — regenerate instead."
        return outcome

    application_url = None
    environment = "QA"
    catalog: list[dict] = []
    explored_page_paths: list[str] = []
    tc = await db.get(TestCase, script.test_case_id) if script.test_case_id else None
    if tc:
        environment = tc.test_phase or "QA"
        # Studio-planned test cases carry the full set of pages the planner
        # crawled — without this the repair loop can only tweak locators
        # and waits, never a wrong navigation target, so a whole class of
        # failures (guessed wait_for_url/url-assertion patterns) survives
        # every repair attempt (observed live 2026-07-12: attempted=4,
        # repaired=0 for exactly this reason).
        explored_page_paths = (tc.metadata_ or {}).get("explored_page_paths") or []
        application = await db.get(ProjectApplication, tc.application_id) if tc.application_id else None
        if application is None:
            application = await resolve_default_application(db, script.project_id)
        if application:
            application_url = resolve_environment_url(application, environment)
            built = await locator_catalog.build_for_application(
                db, project_id=script.project_id, application_id=application.id
            )
            catalog = [
                {
                    "element_name": entry["element_name"],
                    "recommended_locator": entry["recommended_locator"],
                    "business_meaning": entry["business_meaning"],
                }
                for entry in built.entries
            ]

    agent_result = await RepairLoopAgent().run(scripts=[{
        "script_id": script.id,
        "contract": script.contract,
        "framework": script.framework,
        "application_url": application_url,
        "environment": environment,
        "locator_catalog": catalog,
        "explored_page_paths": explored_page_paths,
        "failure": {
            "classification": classification_info.get("classification"),
            "error_message": execution_result.error_message,
            "stack_trace": execution_result.stack_trace,
        },
    }])
    if not agent_result.success or not agent_result.data.get("repairs"):
        outcome["error"] = agent_result.error or "Repair loop produced no result."
        return outcome

    repair = agent_result.data["repairs"][0]
    new_version = await persist_repair_outcome(
        db,
        project_id=script.project_id,
        triggered_by=triggered_by,
        agent_run_id=None,
        parent_script=script,
        repair=repair,
    )
    outcome["attempts"] = [
        {
            "attempt": a.get("attempt"),
            "outcome": a.get("outcome"),
            "detail": a.get("detail"),
            "static_gate_passed": a.get("static_gate_passed"),
            "dry_run_passed": a.get("dry_run_passed"),
        }
        for a in repair.get("attempts", [])
    ]
    outcome["repaired"] = bool(repair.get("resolved"))
    outcome["new_script_id"] = new_version.id if new_version else None
    return outcome


async def classify_failed_results(db: AsyncSession, *, execution_run_id: int) -> int:
    """Classifies every not-yet-classified failed ExecutionResult on a real
    (local subprocess runner) execution run — rules first, LLM assist only
    when rules are inconclusive, same as the automatic dry-run chain's
    failure_classification agent.

    Real executions never went through that chain at all
    (automation_tasks.run_automation_script has no agent wiring), so a
    failure's class was invisible until someone clicked "Repair script" —
    classify_and_repair() would classify on the spot, but only for the one
    result being repaired. Called at the end of both the single-script and
    batch execution tasks so every failure's class is already on the
    ExecutionResult by the time the UI renders it, not just the one a user
    happens to click into.

    Returns the number of results classified.
    """
    from app.agents.execution.failure_classification_agent import (
        REPAIRABLE_CLASSIFICATIONS,
        classify_by_rules,
        classify_with_llm,
    )

    result = await db.execute(
        select(ExecutionResult).where(
            ExecutionResult.execution_run_id == execution_run_id,
            ExecutionResult.status != "pass",
        )
    )
    rows = result.scalars().all()
    classified = 0
    for row in rows:
        if (row.metadata_ or {}).get("failure_classification"):
            continue  # e.g. already classified via an earlier on-demand repair
        result_dict = {
            "error_message": row.error_message,
            "stack_trace": row.stack_trace,
            "network_logs": (row.metadata_ or {}).get("network_logs"),
        }
        classification = classify_by_rules(result_dict)
        if classification:
            source, reason = "rules", f"Matched a deterministic rule for {classification}."
        else:
            classification, reason = await classify_with_llm(result_dict)
            source = "llm"
        row.metadata_ = {
            **(row.metadata_ or {}),
            "failure_classification": {
                "classification": classification,
                "reason": reason,
                "source": source,
                "repairable": classification in REPAIRABLE_CLASSIFICATIONS,
            },
        }
        classified += 1
    if classified:
        await db.flush()
    return classified


_REVIEW_APPROVE_ACTIONS = {"reviewer_approve", "lead_approve", "approve"}  # "approve" = legacy /approve endpoint
_REVIEW_REJECT_ACTIONS = {"reviewer_reject", "lead_reject", "reject"}
_CI_READY_STATUSES = {"ci_ready", "production_regression_candidate"}


async def build_pipeline_stages(db: AsyncSession, script: AutomationScript) -> list[dict]:
    """The real timeline behind a script's status — replaces the abstract,
    status-only lifecycle stepper (which only ever showed "Approved" or
    "Draft", never *when* or *why*) with what actually happened at each
    stage: Discover -> Generate -> Static gate -> Dry-run -> Review ->
    CI-ready.

    Each stage is derived from data that already existed but was never
    surfaced together: discovery from ArtifactLineage (test_case ->
    locator_map, via the AgentRun that produced it), generation from the
    script's own creation, the static gate from static_gate_result, the
    dry run from metadata_.last_dry_run + its ExecutionRun, and review from
    the ApprovalAction audit trail already recorded on every approve/
    reject/lifecycle action.
    """
    from app.models.agent import AgentRun
    from app.models.artifact_lineage import ArtifactLineage

    stages: list[dict] = []

    # ── Discover ──────────────────────────────────────────────────────────
    discover: dict = {"stage": "discover", "state": "pending", "at": None, "detail": None}
    if script.test_case_id is not None:
        lineage_result = await db.execute(
            select(ArtifactLineage)
            .where(
                ArtifactLineage.parent_type == "test_case",
                ArtifactLineage.parent_id == script.test_case_id,
                ArtifactLineage.child_type == "locator_map",
            )
            .order_by(ArtifactLineage.created_at.desc())
            .limit(1)
        )
        lineage = lineage_result.scalar_one_or_none()
        if lineage is not None:
            discover["state"] = "done"
            discover["at"] = lineage.created_at
            if lineage.agent_run_id is not None:
                discovery_run = await db.get(AgentRun, lineage.agent_run_id)
                if discovery_run is not None:
                    discover["at"] = discovery_run.updated_at
                    discover["detail"] = discovery_run.status
    if discover["state"] == "pending":
        discover["detail"] = "No discovery run found for this test case's application yet."
    stages.append(discover)

    # ── Generate ──────────────────────────────────────────────────────────
    attempts = (script.metadata_ or {}).get("generation_attempts") or []
    generate_detail = f"{len(attempts)} attempt(s)" if len(attempts) > 1 else None
    stages.append({"stage": "generate", "state": "done", "at": script.created_at, "detail": generate_detail})

    # ── Static gate ───────────────────────────────────────────────────────
    gate = script.static_gate_result
    if gate is None:
        stages.append({"stage": "static", "state": "pending", "at": None, "detail": None})
    else:
        violation_count = len(gate.get("violations") or [])
        stages.append({
            "stage": "static",
            "state": "done" if gate.get("passed") else "failed",
            "at": script.created_at,
            "detail": f"{violation_count} violation(s)" if violation_count else None,
        })

    # ── Dry run ───────────────────────────────────────────────────────────
    last_dry_run = (script.metadata_ or {}).get("last_dry_run")
    if not last_dry_run:
        stages.append({"stage": "dry_run", "state": "pending", "at": None, "detail": None})
    else:
        dry_run_at = script.updated_at
        execution_run_id = last_dry_run.get("execution_run_id")
        if execution_run_id is not None:
            exec_run = await db.get(ExecutionRun, execution_run_id)
            if exec_run is not None:
                dry_run_at = exec_run.updated_at
        stages.append({
            "stage": "dry_run",
            "state": "done" if last_dry_run.get("passed") else "failed",
            "at": dry_run_at,
            "detail": None if last_dry_run.get("passed") else "Last dry run failed.",
        })

    # ── Review + CI-ready (from the ApprovalAction audit trail) ────────────
    actions, _total = await traceability_service.approval_history(
        db, project_id=script.project_id, entity_type="automation_script", entity_id=script.id,
    )
    review_action = next(
        (a for a in actions if a.action_type.rsplit("_automation_script", 1)[0] in _REVIEW_APPROVE_ACTIONS | _REVIEW_REJECT_ACTIONS),
        None,
    )
    if review_action is None:
        stages.append({"stage": "review", "state": "pending", "at": None, "detail": None})
    else:
        base_action = review_action.action_type.rsplit("_automation_script", 1)[0]
        rejected = base_action in _REVIEW_REJECT_ACTIONS
        stages.append({
            "stage": "review",
            "state": "failed" if rejected else "done",
            "at": review_action.created_at,
            "detail": review_action.notes if rejected else None,
        })

    if script.status in _CI_READY_STATUSES:
        ci_action = next((a for a in actions if a.action_type == "mark_ci_ready_automation_script"), None)
        stages.append({
            "stage": "ci_ready", "state": "done",
            "at": ci_action.created_at if ci_action else script.updated_at, "detail": None,
        })
    else:
        stages.append({"stage": "ci_ready", "state": "pending", "at": None, "detail": None})

    return stages


# Phase 4.6: staged post-generation approval chain, distinct from the
# legacy draft/in_review/approved-or-rejected flow above (`approve_script` /
# `transition_script`), which pre-dates the grounded-generation pipeline and
# is left untouched for scripts still using it. Every step here is additive
# and audited via a dedicated ApprovalAction (see the endpoint), and never
# skips a stage — each action's `from` status is enforced strictly.
# `environment_approve` never changes `status`; it only requires an
# ApprovalAction to exist before `mark_ci_ready` will proceed when the
# script's contract targets PROD_SANITY (see _prod_sanity_gate_satisfied).
LIFECYCLE_APPROVAL_ACTIONS: dict[str, dict[str, str | None]] = {
    "reviewer_approve": {"from": "dry_run_passed", "to": "reviewer_approved"},
    "reviewer_reject": {"from": "dry_run_passed", "to": "rejected"},
    "lead_approve": {"from": "reviewer_approved", "to": "lead_approved"},
    "lead_reject": {"from": "reviewer_approved", "to": "rejected"},
    "environment_approve": {"from": "lead_approved", "to": None},  # no status change
    "mark_ci_ready": {"from": "lead_approved", "to": "ci_ready"},
}


def _requires_prod_sanity_gate(script: AutomationScript) -> bool:
    return (script.contract or {}).get("environmentProfile") == "PROD_SANITY"


async def prod_sanity_gate_satisfied(db: AsyncSession, script: AutomationScript) -> bool:
    """PROD_SANITY scripts must have a recorded environment_approve action
    before they can reach ci_ready — "PROD_SANITY always strict" per the plan."""
    if not _requires_prod_sanity_gate(script):
        return True
    from app.models.approval import ApprovalAction

    result = await db.execute(
        select(ApprovalAction).where(
            ApprovalAction.entity_type == "automation_script",
            ApprovalAction.entity_id == script.id,
            ApprovalAction.action_type == "environment_approve_automation_script",
            ApprovalAction.decision == "approved",
        )
    )
    return result.scalars().first() is not None


async def advance_script_lifecycle(
    db: AsyncSession,
    script: AutomationScript,
    action: str,
    notes: str | None,
) -> AutomationScript:
    spec = LIFECYCLE_APPROVAL_ACTIONS.get(action)
    if spec is None:
        raise ValueError(f"Unknown lifecycle approval action: {action}")
    if script.status != spec["from"]:
        raise ValueError(
            f"Cannot '{action}' a script in status '{script.status}'. "
            f"Expected status '{spec['from']}'."
        )
    if action == "mark_ci_ready" and not await prod_sanity_gate_satisfied(db, script):
        raise ValueError(
            "This script targets PROD_SANITY and requires an environment_approve "
            "action before it can be marked ci_ready."
        )
    if spec["to"] is not None:
        script.status = spec["to"]
    if notes:
        script.metadata_ = {**(script.metadata_ or {}), f"{action}_notes": notes}
    await db.flush()
    await db.refresh(script)
    return script


async def count_scripts_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(AutomationScript.status, func.count())
        .where(AutomationScript.project_id == project_id)
        .group_by(AutomationScript.status)
    )
    return {row[0]: row[1] for row in result.all()}


_FAIL_STATUSES = {"fail", "error", "blocked"}


async def _consecutive_failure_streaks(
    db: AsyncSession, *, project_id: int, test_case_ids: list[int]
) -> dict[int, dict]:
    """For each test case, how many times in a row (most recent first) it
    has failed with the *same* error message, stopping at the first pass or
    a differing error.

    Powers the "retrying this won't change the outcome" warning — a signal
    that was previously invisible: a test case could fail the same way 20+
    times across separate "Retry" clicks and nothing recorded that these
    were repeats of each other, since each ExecutionResult only knows about
    its own run.
    """
    if not test_case_ids:
        return {}
    result = await db.execute(
        select(ExecutionResult.test_case_id, ExecutionResult.status, ExecutionResult.error_message, ExecutionResult.created_at)
        .where(
            ExecutionResult.project_id == project_id,
            ExecutionResult.test_case_id.in_(test_case_ids),
        )
        .order_by(ExecutionResult.test_case_id, ExecutionResult.created_at.desc())
    )
    streaks: dict[int, dict] = {}
    active_tc: int | None = None
    active_error: str | None = None
    broken = False  # True once this tc's streak has been closed off (pass, or an error mismatch)
    for tc_id, status, error_message, _created_at in result.all():
        if tc_id != active_tc:
            active_tc = tc_id
            active_error = None
            broken = False
        if broken:
            continue
        if (status or "").lower() not in _FAIL_STATUSES:
            broken = True  # most-recent-so-far result was a pass — no active streak
            continue
        if active_error is None:
            active_error = error_message
            streaks[tc_id] = {"count": 1, "error_message": error_message}
        elif error_message == active_error:
            streaks[tc_id]["count"] += 1
        else:
            broken = True  # a different error breaks the streak
    return streaks


async def planning_summary(db: AsyncSession, *, project_id: int) -> dict:
    test_case_result = await db.execute(
        select(TestCase)
        .where(
            TestCase.project_id == project_id,
            TestCase.status == "approved",
            TestCase.automation_eligible == "yes",
            # "automation" is the current canonical mode value; "automated" is
            # legacy and "ai" is the AI-assisted flow — all three (plus
            # "hybrid") are automation-applicable. Keep in sync with
            # MODE_VALUES in test_plan_service.py and the automation_only
            # filter in list_test_cases().
            TestCase.execution_mode.in_(["automation", "automated", "hybrid", "ai"]),
            TestCase.is_deleted.is_(False),
        )
        .order_by(TestCase.updated_at.desc(), TestCase.id.desc())
    )
    test_cases = list(test_case_result.scalars().all())

    script_result = await db.execute(
        select(AutomationScript)
        .where(AutomationScript.project_id == project_id)
        .order_by(AutomationScript.updated_at.desc(), AutomationScript.id.desc())
    )
    scripts = list(script_result.scalars().all())

    mapping_result = await db.execute(
        select(AutomationTestMapping)
        .where(
            AutomationTestMapping.project_id == project_id,
            AutomationTestMapping.is_active.is_(True),
        )
        .order_by(AutomationTestMapping.updated_at.desc(), AutomationTestMapping.id.desc())
    )
    mappings = list(mapping_result.scalars().all())

    scripts_by_test_case: dict[int, list[AutomationScript]] = {}
    for script in scripts:
        if script.test_case_id is None:
            continue
        scripts_by_test_case.setdefault(script.test_case_id, []).append(script)

    mapping_by_test_case = {mapping.test_case_id: mapping for mapping in mappings}
    framework_options = supported_framework_catalog()

    suite_result = await db.execute(select(TestSuite.id, TestSuite.name).where(TestSuite.project_id == project_id))
    suite_name_by_id = {row[0]: row[1] for row in suite_result.all()}

    failure_streaks = await _consecutive_failure_streaks(
        db, project_id=project_id, test_case_ids=[tc.id for tc in test_cases]
    )

    candidates: list[dict] = []
    for test_case in test_cases:
        related_scripts = scripts_by_test_case.get(test_case.id, [])
        latest_script = related_scripts[0] if related_scripts else None
        mapping = mapping_by_test_case.get(test_case.id)

        suitability = suitability_assessment(test_case)
        framework_fit = assess_framework_fit(test_case)

        metadata = latest_script.metadata_ if latest_script else {}
        mapping_status = "mapped" if mapping else "mapping_required"

        if latest_script is None:
            handoff = "draft_generation"
        elif latest_script.status in {"draft", "pending_approval", "rejected"}:
            handoff = "human_review"
        elif latest_script.status == "approved" and not test_case.last_automation_status:
            handoff = "repository_ready"
        else:
            handoff = "ready_for_execution"

        # Surfaces the same signals execution_blocked_reason() gates on, so
        # the UI can show *why* a script isn't runnable instead of a bare
        # "not eligible" — these were already computed and stored on every
        # script but never read back out anywhere before.
        script_grounding = metadata.get("grounding") if isinstance(metadata, dict) else None
        script_last_dry_run = metadata.get("last_dry_run") if isinstance(metadata, dict) else None
        blocked_reason = execution_blocked_reason(latest_script) if latest_script else None
        streak = failure_streaks.get(test_case.id)

        candidates.append(
            {
                "test_case_id": test_case.id,
                "test_case_key": test_case.test_case_id,
                "title": test_case.title,
                "test_type": test_case.test_type,
                "automation_status": test_case.automation_status,
                "automation_ready": bool(test_case.automation_ready),
                "mapping_status": mapping_status,
                "execution_handoff": handoff,
                "recommended_framework": framework_fit["recommended_framework"],
                "secondary_framework": framework_fit["secondary_framework"],
                "hybrid_ready": framework_fit["hybrid_ready"],
                "recommended_language": framework_language(framework_fit["recommended_framework"]),
                "assessment_score": suitability["score"],
                "assessment_band": suitability["band"],
                "assessment_reasons": suitability["reasons"],
                "framework_reasons": framework_fit["reasons"],
                "framework_scores": framework_fit["framework_scores"],
                "script_id": latest_script.id if latest_script else None,
                "linked_script_ids": [script.id for script in related_scripts],
                "script_status": latest_script.status if latest_script else None,
                "grounded": script_grounding.get("grounded") if script_grounding else None,
                "ungrounded_element_count": len(script_grounding.get("ungrounded_elements") or []) if script_grounding else 0,
                "last_dry_run_passed": script_last_dry_run.get("passed") if script_last_dry_run else None,
                "execution_blocked_reason": blocked_reason,
                "consecutive_failure_count": streak["count"] if streak else 0,
                "last_failure_error": streak["error_message"] if streak else None,
                "repository": metadata.get("repository") if isinstance(metadata, dict) else None,
                "branch": metadata.get("branch") if isinstance(metadata, dict) else None,
                "script_path": latest_script.file_path if latest_script else None,
                "last_execution_status": test_case.last_automation_status,
                "last_execution_at": test_case.last_automation_run_at,
                "inferred_suite": metadata.get("suite") if isinstance(metadata, dict) else None,
                "coverage_hint": metadata.get("coverage_hint") if isinstance(metadata, dict) else None,
                "updated_at": latest_script.updated_at if latest_script else test_case.updated_at,
                "framework_options": framework_options,
                "test_suite_id": test_case.test_suite_id,
                "test_suite_name": suite_name_by_id.get(test_case.test_suite_id),
            }
        )

    framework_counter = Counter(candidate["recommended_framework"] for candidate in candidates)
    handoff_counter = Counter(candidate["execution_handoff"] for candidate in candidates)

    applications = await list_applications(db, project_id)
    available_environments = sorted(
        {env for app in applications if app.is_active for env in (app.environment_urls or {})}
    ) or ["development", "staging", "production", "ci"]

    return {
        "project_id": project_id,
        "summary": {
            "total_candidates": len(candidates),
            "ready_for_generation": handoff_counter.get("draft_generation", 0),
            "pending_review": handoff_counter.get("human_review", 0),
            "repository_ready": handoff_counter.get("repository_ready", 0),
            "ready_for_execution": handoff_counter.get("ready_for_execution", 0),
            "by_framework": dict(framework_counter),
            "by_handoff": dict(handoff_counter),
            "supported_frameworks": framework_options,
            "available_environments": available_environments,
            "available_browsers": ["Chromium", "Firefox", "WebKit"],
        },
        "candidates": candidates,
    }


async def get_test_case_or_404(db: AsyncSession, test_case_id: int) -> TestCase:
    result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    test_case = result.scalar_one_or_none()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    return test_case


async def get_mapping(db: AsyncSession, mapping_id: int) -> AutomationTestMapping | None:
    result = await db.execute(select(AutomationTestMapping).where(AutomationTestMapping.id == mapping_id))
    return result.scalar_one_or_none()


async def list_mappings(
    db: AsyncSession,
    *,
    project_id: int,
    test_case_id: int | None = None,
    active_only: bool = False,
) -> list[AutomationTestMapping]:
    stmt = select(AutomationTestMapping).where(AutomationTestMapping.project_id == project_id)
    if test_case_id is not None:
        stmt = stmt.where(AutomationTestMapping.test_case_id == test_case_id)
    if active_only:
        stmt = stmt.where(AutomationTestMapping.is_active.is_(True))
    stmt = stmt.order_by(AutomationTestMapping.updated_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def active_mapping_for_test_case(db: AsyncSession, *, project_id: int, test_case_id: int) -> AutomationTestMapping | None:
    result = await db.execute(
        select(AutomationTestMapping).where(
            AutomationTestMapping.project_id == project_id,
            AutomationTestMapping.test_case_id == test_case_id,
            AutomationTestMapping.is_active.is_(True),
        )
    )
    return result.scalars().first()


def _validate_automatable_test_case(test_case: TestCase) -> None:
    if (test_case.execution_mode or "").lower() != "automated":
        raise HTTPException(status_code=422, detail="Test case must be automated before using automation")
    if (test_case.automation_eligible or "").lower() != "yes":
        raise HTTPException(status_code=422, detail="Test case is not automation eligible")


def _sync_mapping_to_test_case(test_case: TestCase, mapping: AutomationTestMapping) -> None:
    test_case.execution_mode = "automated" if test_case.execution_mode == "manual" else test_case.execution_mode
    test_case.automation_eligible = "yes"
    test_case.automation_status = mapping.automation_status
    test_case.automation_ready = bool(mapping.is_active)
    test_case.external_tool = mapping.external_tool_name
    test_case.suite_id = mapping.external_suite_id
    test_case.external_tc_id = mapping.external_test_case_id
    test_case.automation_script_id = int(mapping.external_script_id) if (mapping.external_script_id or "").isdigit() else test_case.automation_script_id


async def create_mapping(db: AsyncSession, body: AutomationTestMappingCreate) -> AutomationTestMapping:
    test_case = await get_test_case_or_404(db, body.test_case_id)
    if test_case.project_id != body.project_id:
        raise HTTPException(status_code=403, detail="Test case does not belong to this project")
    _validate_automatable_test_case(test_case)
    mapping = AutomationTestMapping(**body.model_dump())
    db.add(mapping)
    await db.flush()
    _sync_mapping_to_test_case(test_case, mapping)
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def update_mapping(db: AsyncSession, mapping: AutomationTestMapping, updates: AutomationTestMappingUpdate) -> AutomationTestMapping:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(mapping, key, value)
    result = await db.execute(select(TestCase).where(TestCase.id == mapping.test_case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        _sync_mapping_to_test_case(test_case, mapping)
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def deactivate_mapping(db: AsyncSession, mapping: AutomationTestMapping) -> AutomationTestMapping:
    mapping.is_active = False
    result = await db.execute(select(TestCase).where(TestCase.id == mapping.test_case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        test_case.automation_ready = False
        test_case.automation_status = "mapping_required" if test_case.execution_mode in {"automated", "hybrid"} else "not_required"
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def run_external_automation(
    db: AsyncSession,
    *,
    project_id: int,
    test_case_ids: list[int],
    environment: str,
    user_id: int,
) -> ExecutionRun:
    mappings = []
    test_cases_by_id = {}
    for test_case_id in test_case_ids:
        test_case = await get_test_case_or_404(db, test_case_id)
        if test_case.project_id != project_id:
            raise HTTPException(status_code=403, detail=f"Test case {test_case_id} does not belong to this project")
        _validate_automatable_test_case(test_case)
        mapping = await active_mapping_for_test_case(db, project_id=project_id, test_case_id=test_case_id)
        if not mapping:
            raise HTTPException(status_code=422, detail=f"Active automation mapping required for {test_case.test_case_id}")
        mappings.append(mapping)
        test_cases_by_id[test_case_id] = test_case

    now = datetime.now(timezone.utc)
    run = ExecutionRun(
        project_id=project_id,
        created_by=user_id,
        triggered_by=user_id,
        execution_id=temporary_id("ER"),
        source_type="external_automation_tool",
        external_tool_name=mappings[0].external_tool_name if mappings else None,
        environment=environment,
        status="running",
        started_at=now,
        total_tests=len(mappings),
        passed=0,
        failed=0,
        skipped=0,
        execution_logs=[],
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)

    result_ids = []
    all_logs = []
    external_run_ids = []
    for mapping in mappings:
        connector = get_automation_connector(mapping.external_tool_name)
        summary = await connector.trigger_execution(mapping, environment)
        external_run_ids.append(summary.external_run_id)
        for external_result in summary.results:
            test_case = test_cases_by_id[mapping.test_case_id]
            status = normalize_status(external_result.status)
            exec_result = ExecutionResult(
                execution_run_id=run.id,
                project_id=project_id,
                test_case_id=mapping.test_case_id,
                automation_mapping_id=mapping.id,
                test_name=test_case.title,
                status=status,
                execution_mode=test_case.execution_mode,
                external_tool_name=mapping.external_tool_name,
                external_test_case_id=mapping.external_test_case_id,
                automation_execution_status=status,
                manual_execution_status="pending" if test_case.execution_mode == "hybrid" else None,
                jira_execution_status=None,
                duration_seconds=external_result.duration_seconds,
                duration_ms=int(external_result.duration_seconds * 1000),
                error_message=external_result.error_message,
                stack_trace=external_result.stack_trace,
                screenshot_url=external_result.screenshot_url,
                video_url=external_result.video_url,
                log_url=external_result.log_url,
                external_result_url=external_result.external_result_url,
                jira_issue_key=test_case.jira_issue_key,
                jira_test_key=test_case.jira_test_key,
                raw_result_json=external_result.raw,
                logs=external_result.logs,
            )
            db.add(exec_result)
            await db.flush()
            await traceability_service.create_lineage_many(
                db,
                project_id=project_id,
                parents=[("test_case", mapping.test_case_id), ("execution_run", run.id)],
                child_type="execution_result",
                child_id=exec_result.id,
                metadata={"automation_mapping_id": mapping.id, "source": "external_automation_tool"},
            )
            result_ids.append(exec_result.id)
            all_logs.extend(external_result.logs)
            mapping.last_synced_at = now
            mapping.automation_status = "automated" if status in {"passed", "failed", "skipped"} else mapping.automation_status
            test_case.automation_status = mapping.automation_status
            test_case.last_automation_status = status
            test_case.last_automation_run_at = now
            test_case.last_execution_run_id = run.id
            test_case.latest_evidence_available = bool(external_result.log_url or external_result.screenshot_url or external_result.video_url)
            test_case.evidence_url = external_result.log_url or external_result.screenshot_url or external_result.video_url

    run.external_run_id = ",".join(external_run_ids)
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.duration_seconds = max((run.completed_at - run.started_at).total_seconds(), 0.0) if run.started_at else None
    run.execution_logs = all_logs
    run.total_tests = len(result_ids)
    run.passed = await _count_results(db, run.id, "passed")
    run.failed = await _count_results(db, run.id, "failed")
    run.skipped = await _count_results(db, run.id, "skipped")
    run.metadata_ = {"result_ids": result_ids, "final_status_source": "jira"}
    await db.flush()
    await db.refresh(run)
    return run


async def sync_external_automation_result(
    db: AsyncSession,
    *,
    mapping: AutomationTestMapping,
    environment: str,
    user_id: int,
) -> ExecutionRun:
    if not mapping.is_active:
        raise HTTPException(status_code=422, detail="Automation mapping is inactive")
    return await run_external_automation(
        db,
        project_id=mapping.project_id,
        test_case_ids=[mapping.test_case_id],
        environment=environment,
        user_id=user_id,
    )


async def execution_history(db: AsyncSession, *, test_case_id: int) -> list[ExecutionResult]:
    stmt = (
        select(ExecutionResult)
        .where(ExecutionResult.test_case_id == test_case_id)
        .options(selectinload(ExecutionResult.tested_by), selectinload(ExecutionResult.blocking_defect))
        .order_by(ExecutionResult.created_at.desc())
        .limit(100)
    )
    return list((await db.execute(stmt)).scalars().all())


async def sync_jira_execution_status(
    db: AsyncSession,
    *,
    test_case_id: int,
    jira_execution_status: str,
    jira_issue_key: str | None,
    jira_test_key: str | None,
) -> ExecutionResult:
    status = normalize_status(jira_execution_status)
    test_case = await get_test_case_or_404(db, test_case_id)
    if jira_issue_key:
        test_case.jira_issue_key = jira_issue_key
    if jira_test_key:
        test_case.jira_test_key = jira_test_key
    test_case.jira_final_status = status
    test_case.jira_sync_status = "synced"
    test_case.jira_last_synced_at = datetime.now(timezone.utc)
    test_case.jira_sync_error = None

    latest = (
        await db.execute(
            select(ExecutionResult)
            .where(ExecutionResult.test_case_id == test_case_id)
            .order_by(ExecutionResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        run = ExecutionRun(
            project_id=test_case.project_id,
            created_by=test_case.created_by,
            execution_id=temporary_id("ER"),
            source_type="jira_sync",
            status="completed",
            total_tests=1,
            passed=0,
            failed=0,
            skipped=0,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()
        run.execution_id = display_id("ER", run.id)
        latest = ExecutionResult(
            execution_run_id=run.id,
            project_id=test_case.project_id,
            test_case_id=test_case.id,
            test_name=test_case.title,
            status=status,
            execution_mode=test_case.execution_mode,
        )
        db.add(latest)
    latest.jira_execution_status = status
    latest.jira_issue_key = jira_issue_key or latest.jira_issue_key or test_case.jira_issue_key
    latest.jira_test_key = jira_test_key or latest.jira_test_key or test_case.jira_test_key
    latest.status = status
    latest.metadata_ = {**(latest.metadata_ or {}), "final_status_source": "jira", "jira_synced_at": datetime.now(timezone.utc).isoformat()}
    await db.flush()
    await db.refresh(latest)
    return latest


async def latest_jira_execution_status(db: AsyncSession, *, test_case_id: int) -> dict:
    latest = (
        await db.execute(
            select(ExecutionResult)
            .where(ExecutionResult.test_case_id == test_case_id)
            .order_by(ExecutionResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    test_case = await get_test_case_or_404(db, test_case_id)
    jira_status = latest.jira_execution_status if latest else None
    return {
        "test_case_id": test_case_id,
        "jira_issue_key": (latest.jira_issue_key if latest else None) or test_case.jira_issue_key,
        "jira_test_key": (latest.jira_test_key if latest else None) or test_case.jira_test_key,
        "jira_execution_status": jira_status or test_case.jira_final_status,
        "final_qa_status": jira_status or test_case.jira_final_status or "Pending Jira Status",
        "source": "jira",
    }


async def _count_results(db: AsyncSession, run_id: int, status: str) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(ExecutionResult).where(
                    ExecutionResult.execution_run_id == run_id,
                    ExecutionResult.automation_execution_status == status,
                )
            )
        ).scalar_one()
    )
