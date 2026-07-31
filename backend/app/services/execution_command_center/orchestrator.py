"""Suite-level orchestration over the existing single-script runner.

`automation_runner` already knows how to execute one compiled script and return a
normalized `RunnerResult`. This module is what turns a published suite snapshot
into a governed sequence of those calls, with the gate in front, the eight
outcomes behind, and a persisted event stream throughout.

Nothing here renders code, judges quality, or invents a runner. Nothing here
re-implements the readiness probes or the classifier either — `readiness.py` and
`outcomes.py` own those, and this module's job is to supply them with facts and
persist what they conclude.

Expectations come from the Automation IR, not from this module. The IR's
`assertions[]` is built exclusively from checkpoints a human accepted
(`recorder/ir_emitter.py`, Section 16), which is what makes a PASS here grounded
rather than asserted by the orchestrator itself.

**A known limitation, stated rather than papered over.** Automation IR v1.0 can
only express UI assertions — `visible`, `text`, `value`, `url` (see
`CHECKPOINT_ASSERTIONS` in the emitter). The P1-S7 checklist also asks for
deterministic business assertions across order, billing, charging, inventory and
provisioning. There is no IR construct, checkpoint type or adapter that produces
them, so this slice records every assertion with `source='ui'` and does not
pretend to evaluate a backend expectation. The other sources remain in the
vocabulary for the adapter work that would deliver them.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_script import AutomationScript
from app.models.automation_suite import (
    AutomationSuite,
    AutomationSuiteSnapshot,
    AutomationSuiteTestCase,
)
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.execution_command_center import (
    ExecutionRunAssertion,
    ExecutionRunEvidence,
    ExecutionRunItem,
    ExecutionRunItemStep,
)
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario
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
from app.services.execution_command_center import events, outcomes, readiness
from app.services.project_application_service import resolve_environment_url

ITEM_TIMEOUT_SECONDS = 600

# Follows the vocabulary already in use on this column: automation_local,
# automation_local_batch, repair_dry_run, asset_dry_run. Set explicitly because
# the column is NOT NULL in the database while the model annotates it nullable.
SOURCE_TYPE = "automation_suite_run"

# IR v1.0 assertion type -> our assertion source. Every one is a UI assertion;
# see the module docstring for why nothing maps to api/db/oms/billing yet.
_ASSERTION_SOURCE_BY_IR_TYPE = {
    "visible": "ui",
    "text": "ui",
    "value": "ui",
    "url": "ui",
}

# Evidence the runner can actually return, keyed by the IR's `evidenceRequired`
# vocabulary. A required type outside this map is recorded as `unavailable` with a
# reason instead of being dropped — that is what lets it drive INCONCLUSIVE.
_CAPTURE_SUPPORTED = ("screenshot", "trace", "log", "console", "network", "api")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Creating a run ──────────────────────────────────────────────────────────


async def _snapshot_for_suite(
    db: AsyncSession, suite: AutomationSuite
) -> AutomationSuiteSnapshot:
    snapshot = (
        await db.execute(
            select(AutomationSuiteSnapshot)
            .where(AutomationSuiteSnapshot.suite_id == suite.id)
            .order_by(AutomationSuiteSnapshot.suite_version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise AutomationSuiteError(
            409,
            "NO_SNAPSHOT",
            "This suite has no published snapshot. Publish the suite before executing it.",
        )
    return snapshot


async def create_suite_run(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    actor_id: int,
    environment: str | None = None,
    execution_purpose: str | None = None,
    trigger_source: str = "user",
) -> ExecutionRun:
    """Create a run for a published suite, gate it, and expand its scope.

    The run row is created whether or not the gate passes. A blocked run is a
    first-class record: the operator needs to see the scope and the blocker, and
    "why was this refused" must survive the environment recovering.
    """
    if suite.status != "PUBLISHED":
        raise AutomationSuiteError(
            409,
            "SUITE_NOT_PUBLISHED",
            f"Only a published suite can be executed. This suite is {suite.status}.",
        )

    snapshot = await _snapshot_for_suite(db, suite)
    members: list[dict[str, Any]] = list(snapshot.members or [])
    if not members:
        raise AutomationSuiteError(
            409, "EMPTY_SNAPSHOT", "The published snapshot contains no members to execute."
        )

    resolved_environment = environment or suite.default_environment
    frameworks = {
        (m.get("framework") or "").lower() for m in members if m.get("framework")
    }
    # The application to gate on. A mixed-application suite is gated on the
    # first-declared one; per-item application readiness is re-checked at
    # dispatch, so this is a fast-fail, not the only check.
    application_id = next(
        (m.get("application_id") for m in members if m.get("application_id")), None
    )

    correlation_id = suite.correlation_id or f"suite-{suite.id}-{uuid.uuid4().hex[:8]}"

    run = ExecutionRun(
        project_id=suite.project_id,
        created_by=actor_id,
        triggered_by=actor_id,
        execution_id=f"EXE-{_now():%Y%m%d}-{uuid.uuid4().hex[:6].upper()}",
        suite_name=suite.name,
        environment=resolved_environment,
        status="pending",
        execution_type="automation",
        source_type=SOURCE_TYPE,
        suite_id=suite.id,
        suite_snapshot_id=snapshot.id,
        lifecycle_state="READINESS_PENDING",
        trigger_source=trigger_source,
        execution_purpose=execution_purpose,
        correlation_id=correlation_id,
        # Sequential in this slice. The column exists so raising it is a
        # configuration change rather than a schema change.
        parallel_limit=1,
        total_tests=len(members),
    )
    db.add(run)
    await db.flush()

    gate = await readiness.check_suite_run_readiness(
        db,
        application_id=application_id,
        environment=resolved_environment,
        frameworks=frameworks or {"playwright"},
    )
    run.readiness = gate.as_dict()
    run.readiness_checked_at = _now()

    await _expand_items(db, run, snapshot, suite)

    await events.emit(
        db,
        run.id,
        event_type="run_readiness_evaluated",
        message=(
            "All readiness axes passed."
            if gate.ready
            else f"{len(gate.blockers)} readiness blocker(s) prevent this run from starting."
        ),
        payload=gate.as_dict(),
    )

    if not gate.ready:
        run.lifecycle_state = "BLOCKED_BEFORE_START"
        run.status = "failed"
        await events.emit(
            db,
            run.id,
            event_type="run_blocked_before_start",
            message="; ".join(b.detail for b in gate.blockers),
            payload={"blockers": [b.as_dict() for b in gate.blockers]},
        )
    else:
        run.lifecycle_state = "QUEUED"
        run.status = "queued"
        await events.emit(
            db,
            run.id,
            event_type="run_queued",
            message=f"{len(members)} test case(s) queued for execution.",
        )

    await _recount_evidence(db, run)
    return run


async def _expand_items(
    db: AsyncSession,
    run: ExecutionRun,
    snapshot: AutomationSuiteSnapshot,
    suite: AutomationSuite,
) -> list[ExecutionRunItem]:
    """One item per snapshot member, in the snapshot's own order.

    `order_index` is assigned here once and never rewritten, so Section 6.2's
    "Reset order" always has an authoritative order to return to. Members are
    ordered by their planned sequence where the suite declared one, falling back
    to the snapshot's stable member_id ordering.
    """
    members = sorted(
        (snapshot.members or []),
        key=lambda m: (
            m.get("planned_sequence") if m.get("planned_sequence") is not None else 10**9,
            m.get("member_id") or 0,
        ),
    )

    items: list[ExecutionRunItem] = []
    for index, member in enumerate(members, start=1):
        test_case = None
        if member.get("test_case_id"):
            test_case = await db.get(TestCase, member["test_case_id"])

        # The business journey. A TestScenario is what this platform models a
        # journey as, so the item's journey is its scenario's title — not a
        # module or folder name, neither of which TestCase carries.
        journey = None
        if test_case is not None and test_case.scenario_id:
            scenario = (
                await db.execute(
                    select(TestScenario).where(TestScenario.id == test_case.scenario_id)
                )
            ).scalar_one_or_none()
            journey = scenario.title if scenario is not None else None

        item = ExecutionRunItem(
            execution_run_id=run.id,
            project_id=run.project_id,
            order_index=index,
            suite_test_case_id=member.get("member_id"),
            test_case_id=member.get("test_case_id"),
            execution_group_id=member.get("execution_group_id"),
            script_id=member.get("script_id"),
            application_id=member.get("application_id"),
            # Frozen display identity — the matrix must render what was published
            # even if the live test case is later renamed or deleted.
            test_case_key=(test_case.test_case_id if test_case else None),
            title=(test_case.title if test_case else None),
            journey=journey,
            priority=(test_case.priority if test_case else None),
            framework=member.get("framework"),
            environment=member.get("environment") or run.environment,
            test_case_version=member.get("test_case_version"),
            lifecycle_state="QUEUED",
            result="PENDING",
            snapshot_member=member,
        )
        db.add(item)
        items.append(item)

    await db.flush()

    for item in items:
        await _seed_expectations(db, run, item, suite)

    await db.flush()
    return items


async def _seed_expectations(
    db: AsyncSession,
    run: ExecutionRun,
    item: ExecutionRunItem,
    suite: AutomationSuite,
) -> None:
    """Create the item's steps, assertions and required-evidence rows from the IR.

    Seeded before dispatch on purpose: the inspector must be able to show "6 of
    14" and the mandatory-evidence expectation *before* the item runs, and the
    quorum rule needs rows to check against rather than a runner's opinion after
    the fact.
    """
    member = None
    if item.suite_test_case_id is not None:
        member = await db.get(AutomationSuiteTestCase, item.suite_test_case_id)

    contract: dict[str, Any] | None = None
    if member is not None:
        draft = await ir_service.current_draft(db, member, suite)
        if draft is not None and draft.contract:
            contract = draft.contract
    if contract is None and item.script_id is not None:
        script = await db.get(AutomationScript, item.script_id)
        if script is not None and script.contract:
            contract = script.contract

    if not contract:
        # No IR means no declared expectation. Recorded on the item rather than
        # guessed at: classification will land INCONCLUSIVE, which is the honest
        # outcome for a test that declares nothing to prove.
        item.attention_reason = (
            "No Automation IR or script contract was found for this member, so no "
            "assertion or evidence expectation could be established."
        )
        return

    steps = contract.get("steps") or []
    for position, step in enumerate(steps, start=1):
        db.add(
            ExecutionRunItemStep(
                execution_run_item_id=item.id,
                step_number=position,
                action_text=(step.get("description") or step.get("action") or None),
                expected_text=step.get("expectedResult") or None,
                status="pending",
                application_context=step.get("application") or None,
            )
        )
    item.steps_total = len(steps)

    assertions = contract.get("assertions") or []
    for assertion in assertions:
        ir_type = (assertion.get("type") or "").lower()
        db.add(
            ExecutionRunAssertion(
                execution_run_item_id=item.id,
                # Every IR v1.0 assertion is a UI assertion. Defaulting unknown
                # types to 'ui' rather than inventing a backend source keeps the
                # source field truthful.
                source=_ASSERTION_SOURCE_BY_IR_TYPE.get(ir_type, "ui"),
                description=(
                    f"{ir_type or 'assertion'} on {assertion.get('target') or 'page'}"
                ),
                expected_value=str(assertion.get("expected") or "") or None,
                # Every accepted checkpoint is mandatory: a human accepted it
                # precisely because it must hold.
                mandatory=True,
                passed=None,
            )
        )
    item.assertions_total = len(assertions)

    for evidence_type in contract.get("evidenceRequired") or []:
        normalized = str(evidence_type).lower()
        supported = normalized in _CAPTURE_SUPPORTED
        db.add(
            ExecutionRunEvidence(
                execution_run_id=run.id,
                execution_run_item_id=item.id,
                evidence_type=normalized if normalized in _CAPTURE_SUPPORTED else "log",
                status="pending" if supported else "unavailable",
                mandatory=True,
                unavailable_reason=(
                    None
                    if supported
                    else (
                        f"Evidence type '{normalized}' is required by the IR but no "
                        "capture path exists in this release. It is reported as "
                        "missing rather than omitted, so the outcome is INCONCLUSIVE "
                        "rather than a false pass."
                    )
                ),
            )
        )
    item.evidence_required = len(contract.get("evidenceRequired") or [])


async def _recount_evidence(db: AsyncSession, run: ExecutionRun) -> None:
    """Refresh the run's evidence rollup from the rows themselves."""
    # Same autoflush=False caveat as _recount_item.
    await db.flush()
    rows = (
        await db.execute(
            select(ExecutionRunEvidence).where(
                ExecutionRunEvidence.execution_run_id == run.id
            )
        )
    ).scalars().all()
    mandatory = [r for r in rows if r.mandatory]
    run.evidence_required_total = len(mandatory)
    run.evidence_captured_total = sum(1 for r in mandatory if r.status == "captured")


# ── Dispatching one item ────────────────────────────────────────────────────


async def _base_url(db: AsyncSession, item: ExecutionRunItem) -> str | None:
    if item.application_id is None:
        return None
    application = await db.get(ProjectApplication, item.application_id)
    if application is None:
        return None
    return resolve_environment_url(application, item.environment)


async def dispatch_item(db: AsyncSession, run: ExecutionRun, item: ExecutionRunItem) -> None:
    """Execute one item and persist everything it produced.

    Every early return classifies the item rather than raising: a member that
    cannot run is a governed outcome (BLOCKED, POLICY_BLOCKED,
    AUTOMATION_FAILURE), not an orchestration crash that would abandon the rest
    of the suite.
    """
    item.lifecycle_state = "STARTING"
    item.started_at = _now()
    await events.emit(
        db,
        run.id,
        event_type="item_started",
        message=f"{item.test_case_key or 'Test case'} started.",
        item_id=item.id,
    )

    facts_kwargs: dict[str, Any] = {}
    framework = (item.framework or "").lower()

    if item.script_id is None:
        facts_kwargs["blocked_reason"] = (
            "This member has no compiled script in the published snapshot, so there "
            "is nothing to execute."
        )
    elif not framework:
        facts_kwargs["blocked_reason"] = "The snapshot declares no framework for this member."
    else:
        available, detail = is_available(framework)
        if not available:
            # Contract Section 2.1.8: a framework with no registered runner is
            # BLOCKED with the runner's own reason, never reported as passing.
            facts_kwargs["blocked_reason"] = detail

    runner_result = None
    per_test = None

    if not facts_kwargs:
        script = await db.get(AutomationScript, item.script_id)
        compiled_files = (script.compiled_files or {}) if script else {}
        if script is None:
            facts_kwargs["blocked_reason"] = "The compiled script row is missing."
        elif not compiled_files:
            facts_kwargs["blocked_reason"] = (
                "This script has no compiled bundle. Recompile the asset before "
                "including it in an execution."
            )
        else:
            workspace: Path = reset_workspace(f"run-{run.id}-item-{item.id}")
            if framework == "playwright":
                write_playwright_config(
                    workspace,
                    base_url=await _base_url(db, item),
                    test_dir="specs" if compiled_files else ".",
                )
            else:
                write_pytest_config(workspace)
            materialize_bundle(workspace=workspace, compiled_files=compiled_files)
            script_file = script.file_path or next(iter(compiled_files))

            item.lifecycle_state = "RUNNING"
            runner_result = await run_script_for_execution(
                framework=framework,
                workspace=workspace,
                script_file_name=script_file,
                execution_command=script.execution_command,
                environment=item.environment,
                timeout_seconds=ITEM_TIMEOUT_SECONDS,
            )
            item.runner_name = str(runner_result.metadata.get("runner") or "")[:100] or None

            if runner_result.results:
                per_test = runner_result.results[0]
            elif runner_result.error_message:
                # The runner could not start or produced nothing. That is the
                # harness failing, not the application — Section 10.
                facts_kwargs["automation_failure_reason"] = runner_result.error_message
            else:
                facts_kwargs["automation_failure_reason"] = (
                    "The runner completed without reporting any test result."
                )

    if per_test is not None:
        await _persist_runner_evidence(db, run, item, runner_result, per_test)
        # Playwright fails the test if any web-first assertion fails, so a green
        # test means every declared assertion held. The converse is not
        # attributable per-assertion, so a failure leaves them unevaluated and
        # the classifier decides from the runner verdict — see outcomes.py.
        if per_test.status == "pass":
            await _mark_assertions_passed(db, item)
        item.duration_ms = per_test.duration_ms
        item.error_message = per_test.error_message

    await _recount_item(db, item)

    facts = outcomes.ItemFacts(
        runner_status=(per_test.status if per_test else None),
        assertions=tuple(await _assertion_facts(db, item)),
        evidence=tuple(await _evidence_facts(db, item)),
        **facts_kwargs,
    )
    classification = outcomes.classify_item(facts)

    item.result = classification.result
    # Preserve a reason already recorded at seeding time (e.g. "no IR found")
    # rather than overwriting the more specific explanation.
    item.attention_reason = classification.attention_reason or item.attention_reason
    item.lifecycle_state = "COMPLETED"
    item.completed_at = _now()

    await _write_portable_result(db, run, item, runner_result, per_test)

    await events.emit(
        db,
        run.id,
        event_type="item_result_finalized",
        message=(
            f"{item.test_case_key or 'Test case'} finalized as {item.result}"
            + (f": {item.attention_reason}" if item.attention_reason else ".")
        ),
        item_id=item.id,
        payload={
            "result": item.result,
            "evidence_captured": item.evidence_captured,
            "evidence_required": item.evidence_required,
            "assertions_passed": item.assertions_passed,
            "assertions_total": item.assertions_total,
        },
    )


async def _mark_assertions_passed(db: AsyncSession, item: ExecutionRunItem) -> None:
    rows = (
        await db.execute(
            select(ExecutionRunAssertion).where(
                ExecutionRunAssertion.execution_run_item_id == item.id
            )
        )
    ).scalars().all()
    for row in rows:
        row.passed = True
        row.evaluated_at = _now()


async def _assertion_facts(
    db: AsyncSession, item: ExecutionRunItem
) -> list[outcomes.AssertionFact]:
    rows = (
        await db.execute(
            select(ExecutionRunAssertion).where(
                ExecutionRunAssertion.execution_run_item_id == item.id
            )
        )
    ).scalars().all()
    return [outcomes.AssertionFact(mandatory=r.mandatory, passed=r.passed) for r in rows]


async def _evidence_facts(
    db: AsyncSession, item: ExecutionRunItem
) -> list[outcomes.EvidenceFact]:
    rows = (
        await db.execute(
            select(ExecutionRunEvidence).where(
                ExecutionRunEvidence.execution_run_item_id == item.id
            )
        )
    ).scalars().all()
    return [
        outcomes.EvidenceFact(
            evidence_type=r.evidence_type, mandatory=r.mandatory, status=r.status
        )
        for r in rows
    ]


async def _persist_runner_evidence(
    db: AsyncSession,
    run: ExecutionRun,
    item: ExecutionRunItem,
    runner_result: Any,
    per_test: Any,
) -> None:
    """Fulfil pending evidence rows from what the runner actually returned.

    A pending row whose artifact never arrived is switched to `unavailable` with
    a reason, not deleted — that is precisely what allows the quorum rule to
    produce INCONCLUSIVE instead of a silent pass.
    """
    produced: dict[str, tuple[str | None, dict | None]] = {}
    if per_test.screenshot_path:
        produced["screenshot"] = (per_test.screenshot_path, None)
    if per_test.trace_path:
        produced["trace"] = (per_test.trace_path, None)
    if runner_result.log_path:
        produced["log"] = (runner_result.log_path, None)
    if per_test.console_logs:
        produced["console"] = (None, {"entries": per_test.console_logs})
    if per_test.network_logs:
        produced["network"] = (None, {"entries": per_test.network_logs})
        # The network capture is also the API evidence for this slice: it is the
        # request/response record the compiler attaches via testInfo.attach.
        produced["api"] = (None, {"entries": per_test.network_logs})

    pending = (
        await db.execute(
            select(ExecutionRunEvidence).where(
                ExecutionRunEvidence.execution_run_item_id == item.id,
                ExecutionRunEvidence.status == "pending",
            )
        )
    ).scalars().all()

    for row in pending:
        artifact = produced.get(row.evidence_type)
        if artifact is None:
            row.status = "unavailable"
            row.unavailable_reason = (
                f"The runner did not produce {row.evidence_type} evidence for this test."
            )
            await events.emit(
                db,
                run.id,
                event_type="evidence_unavailable",
                message=f"{row.evidence_type} evidence was required but not produced.",
                item_id=item.id,
            )
            continue
        file_path, payload = artifact
        row.file_path = file_path
        row.payload = payload
        row.status = "captured"
        row.captured_at = _now()
        # Artifacts are served through an authenticated endpoint that applies the
        # masking pass; nothing is marked sanitized until it has been through it.
        row.sanitized = False
        await events.emit(
            db,
            run.id,
            event_type="evidence_stored",
            message=f"{row.evidence_type} evidence captured.",
            item_id=item.id,
        )

    # Artifacts the runner produced that nothing required are still worth keeping:
    # they are the trace and screenshot an investigator wants on a failure.
    required_types = {r.evidence_type for r in pending}
    for evidence_type, (file_path, payload) in produced.items():
        if evidence_type in required_types:
            continue
        db.add(
            ExecutionRunEvidence(
                execution_run_id=run.id,
                execution_run_item_id=item.id,
                evidence_type=evidence_type,
                status="captured",
                mandatory=False,
                file_path=file_path,
                payload=payload,
                captured_at=_now(),
            )
        )


async def _recount_item(db: AsyncSession, item: ExecutionRunItem) -> None:
    # The session is created with autoflush=False (see app/database.py), so rows
    # added by _persist_runner_evidence are invisible to the SELECTs below until
    # they are flushed explicitly. Without this the counts silently come back as
    # zero even though the evidence rows commit correctly a moment later.
    await db.flush()
    assertions = await _assertion_facts(db, item)
    evidence = await _evidence_facts(db, item)
    item.assertions_total = len(assertions)
    item.assertions_passed = sum(1 for a in assertions if a.passed is True)
    item.evidence_required = sum(1 for e in evidence if e.mandatory)
    item.evidence_captured = sum(
        1 for e in evidence if e.mandatory and e.status == "captured"
    )
    item.evidence_total_captured = sum(1 for e in evidence if e.status == "captured")


async def _write_portable_result(
    db: AsyncSession,
    run: ExecutionRun,
    item: ExecutionRunItem,
    runner_result: Any,
    per_test: Any,
) -> None:
    """Also write the shared `ExecutionResult` row.

    The Execution Dashboard, Jira sync and reporting all read `ExecutionResult`.
    Writing it keeps a suite run visible to everything that already exists,
    without pushing the eight-outcome vocabulary into a column shared with manual
    and AI runs — `status` gets the nearest legal value, and the governed outcome
    stays on the item.
    """
    status_map = {
        "PASS": "pass",
        "FAIL": "fail",
        "SKIPPED": "skip",
        "BLOCKED": "blocked",
        "POLICY_BLOCKED": "blocked",
        "INCONCLUSIVE": "error",
        "ENVIRONMENT_FAILURE": "error",
        "DATA_FAILURE": "error",
        "AUTOMATION_FAILURE": "error",
    }
    db.add(
        ExecutionResult(
            execution_run_id=run.id,
            test_case_id=item.test_case_id,
            project_id=run.project_id,
            test_name=(item.title or item.test_case_key or f"item-{item.order_index}"),
            status=status_map.get(item.result, "error"),
            duration_ms=item.duration_ms,
            execution_mode="automation",
            error_message=item.error_message,
            screenshot_url=(per_test.screenshot_path if per_test else None),
            video_url=(per_test.video_path if per_test else None),
            log_url=(runner_result.log_path if runner_result else None),
            automation_mapping_id=None,
            metadata_={
                # The governed outcome, so a consumer of ExecutionResult can see
                # the distinction `status` cannot express.
                "suite_run": True,
                "execution_run_item_id": item.id,
                "governed_outcome": item.result,
                "attention_reason": item.attention_reason,
                "suite_test_case_id": item.suite_test_case_id,
            },
        )
    )


# ── The run loop ────────────────────────────────────────────────────────────


async def next_queued_item(db: AsyncSession, run: ExecutionRun) -> ExecutionRunItem | None:
    return (
        await db.execute(
            select(ExecutionRunItem)
            .where(
                ExecutionRunItem.execution_run_id == run.id,
                ExecutionRunItem.lifecycle_state == "QUEUED",
            )
            .order_by(ExecutionRunItem.order_index)
            .limit(1)
        )
    ).scalar_one_or_none()


async def finalize_run(db: AsyncSession, run: ExecutionRun, *, stopped: bool = False) -> None:
    """Classify the run and close it out."""
    results = (
        await db.execute(
            select(ExecutionRunItem.result).where(ExecutionRunItem.execution_run_id == run.id)
        )
    ).scalars().all()
    executed = [r for r in results if r != "PENDING"]

    run.outcome = outcomes.classify_run(list(executed))
    run.passed = sum(1 for r in results if r == "PASS")
    run.failed = sum(1 for r in results if r == "FAIL")
    run.skipped = sum(1 for r in results if r == "SKIPPED")
    run.total_tests = len(results)
    run.completed_at = _now()
    if run.started_at:
        run.duration_seconds = (run.completed_at - run.started_at).total_seconds()

    if run.lifecycle_state not in ("CANCELLED", "STOPPED"):
        run.lifecycle_state = "STOPPED" if stopped else "COMPLETED"
    run.status = "completed"
    run.run_version = (run.run_version or 0) + 1
    run.pending_command = None

    await _recount_evidence(db, run)
    await events.emit(
        db,
        run.id,
        event_type="run_finalized",
        message=f"Run finalized as {run.outcome} ({len(executed)} of {len(results)} executed).",
        payload={
            "outcome": run.outcome,
            "lifecycle_state": run.lifecycle_state,
            "executed": len(executed),
            "total": len(results),
        },
    )
