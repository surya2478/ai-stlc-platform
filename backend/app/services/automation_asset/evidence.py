"""UI-020/021/023 — evidence gathering for the autonomy policy.

This is the ONLY module in the package that queries the database, mirroring the
discipline UI-018 established with `automation_suite/inheritance.py`: one
gathering pass, then pure functions over frozen dataclasses. Keeping the reads
here is what bounds cost and what makes `autonomy.evaluate` unit-testable
without a session.

Nothing here judges. Every value is a read of a fact some other subsystem
already computed — the Static Quality Gate's persisted verdict, the IR
emitter's readiness map, the locator map, execution history, suite gaps. The
verdict is formed in `autonomy.py` from what this module reports.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_script import AutomationScript
from app.models.automation_suite import AutomationSuite, AutomationSuiteGap, AutomationSuiteTestCase
from app.models.execution import ExecutionResult
from app.models.locator_map import LocatorMapEntry
from app.models.recording_session import AutomationIrDraft
from app.models.test_case import TestCase
from app.services.automation_asset.autonomy import AssetEvidence

# Steps whose target must resolve to a real element — mirrors
# ELEMENT_REQUIRED_ACTIONS in generation_contract.py. Kept as its own constant
# rather than imported because this one answers a different question ("does the
# asset drive UI elements at all") and must not silently follow a change to the
# validator's list.
_ELEMENT_DRIVEN_ACTIONS = frozenset(
    {"fill", "click", "check", "uncheck", "select", "hover", "wait_for_visible"}
)

# Matches automation_confidence_service._dry_run_stability: dry runs are not
# indexed, so the scan is capped and filtered in Python.
_EXECUTION_SCAN_LIMIT = 200


def _contract_locator_names(contract: dict | None) -> set[str]:
    if not contract:
        return set()
    names: set[str] = set()
    for page_object in contract.get("pageObjects") or []:
        for element in page_object.get("elements") or []:
            name = element.get("name")
            if name:
                names.add(name)
    return names


def _element_driven_step_count(contract: dict | None) -> int:
    if not contract:
        return 0
    return sum(
        1
        for step in (contract.get("steps") or [])
        if step.get("action") in _ELEMENT_DRIVEN_ACTIONS
    )


def _custom_step_count(contract: dict | None) -> int:
    if not contract:
        return 0
    return sum(1 for step in (contract.get("steps") or []) if step.get("action") == "custom")


async def _current_ir_draft(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> AutomationIrDraft | None:
    result = await db.execute(
        select(AutomationIrDraft)
        .where(
            AutomationIrDraft.suite_id == suite.id,
            AutomationIrDraft.test_case_id == member.test_case_id,
            AutomationIrDraft.is_current.is_(True),
        )
        .order_by(AutomationIrDraft.version.desc(), AutomationIrDraft.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _resolved_script(
    db: AsyncSession, member: AutomationSuiteTestCase
) -> AutomationScript | None:
    """The script this member's evaluation resolved against.

    `resolved_script_id` is recomputed on every suite evaluation, so it is the
    authoritative pointer. Falling back to "newest script for this test case"
    would risk scoring a version the suite has not accepted.
    """
    if member.resolved_script_id is None:
        return None
    return await db.get(AutomationScript, member.resolved_script_id)


async def _grounded_locator_count(
    db: AsyncSession, *, project_id: int, application_id: int | None, names: set[str]
) -> int:
    if not names or application_id is None:
        return 0
    result = await db.execute(
        select(func.count(func.distinct(LocatorMapEntry.element_name))).where(
            LocatorMapEntry.project_id == project_id,
            LocatorMapEntry.application_id == application_id,
            LocatorMapEntry.element_name.in_(names),
        )
    )
    return int(result.scalar() or 0)


async def _dry_run_counts(
    db: AsyncSession, *, project_id: int, script_id: int | None
) -> tuple[int, int]:
    """(passing, total) dry runs for this script.

    Reads the same shape `automation_confidence_service._dry_run_stability`
    reads, so the precondition and the score dimension can never disagree about
    what a dry run is.
    """
    if script_id is None:
        return 0, 0
    result = await db.execute(
        select(ExecutionResult)
        .where(ExecutionResult.project_id == project_id)
        .order_by(ExecutionResult.id.desc())
        .limit(_EXECUTION_SCAN_LIMIT)
    )
    matches = [
        row
        for row in result.scalars().all()
        if (row.metadata_ or {}).get("automation_script_id") == script_id
        and (row.metadata_ or {}).get("dry_run")
    ]
    passing = sum(1 for row in matches if row.status == "pass")
    return passing, len(matches)


async def _unwaived_critical_gaps(
    db: AsyncSession, member: AutomationSuiteTestCase
) -> int:
    """Critical gaps on this member that are still blocking.

    Only `status='open'` counts. `exception_approved` and `excluded` are human
    adjudications that deliberately stop a finding blocking (UI-018), and
    `resolved` is what re-evaluation writes when the finding no longer applies.
    """
    result = await db.execute(
        select(func.count(AutomationSuiteGap.id)).where(
            AutomationSuiteGap.suite_test_case_id == member.id,
            AutomationSuiteGap.severity == "critical",
            AutomationSuiteGap.status == "open",
        )
    )
    return int(result.scalar() or 0)


async def gather(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
) -> tuple[AssetEvidence, AutomationIrDraft | None, AutomationScript | None]:
    """One gathering pass for one suite member.

    Returns the evidence plus the two artifact rows it was gathered from, so the
    caller can record `ir_draft_id` / `script_id` on the decision without
    querying for them again.
    """
    draft = await _current_ir_draft(db, member, suite)
    script = await _resolved_script(db, member)

    # Prefer the IR draft's contract; fall back to the contract the script was
    # compiled from, so an asset generated outside the recorder is still
    # evaluable.
    contract = (draft.contract if draft else None) or (script.contract if script else None)
    readiness = (draft.readiness if draft else None) or {}

    locator_names = _contract_locator_names(contract)

    test_case = await db.get(TestCase, member.test_case_id)
    application_id = member.resolved_application_id or (
        test_case.application_id if test_case else None
    )

    grounded = await _grounded_locator_count(
        db,
        project_id=suite.project_id,
        application_id=application_id,
        names=locator_names,
    )
    passing_runs, total_runs = await _dry_run_counts(
        db, project_id=suite.project_id, script_id=script.id if script else None
    )
    critical_gaps = await _unwaived_critical_gaps(db, member)

    gate = (script.static_gate_result if script else None) or None
    blocking = len((gate or {}).get("violations") or [])

    # Score is computed by the existing confidence service, which returns 0-1.
    # It is scaled to 0-100 here because the threshold and every stored decision
    # are expressed on a 100-point scale.
    score = None
    dimensions: dict[str, float] = {}
    if script is not None:
        from app.services import automation_confidence_service

        try:
            raw = await automation_confidence_service.compute_confidence_score(db, script)
            score = round(float(raw["overall"]) * 100, 2)
            dimensions = {k: v for k, v in raw.items() if k != "overall"}
        except Exception:
            # A score that cannot be computed must read as "unknown", never as a
            # default pass — autonomy.evaluate holds the asset when score is None.
            score = None
            dimensions = {}

    evidence = AssetEvidence(
        static_gate_ran=gate is not None,
        static_gate_passed=(gate or {}).get("passed") if gate is not None else None,
        blocking_violation_count=blocking,
        has_ir=contract is not None,
        custom_step_count=_custom_step_count(contract) if contract is not None else None,
        ir_unresolved_count=readiness.get("unresolved_count") if readiness else 0,
        element_step_count=_element_driven_step_count(contract),
        referenced_locator_count=len(locator_names),
        grounded_locator_count=grounded,
        passing_dry_runs=passing_runs,
        total_dry_runs=total_runs,
        unwaived_critical_gaps=critical_gaps,
        score=score,
        dimensions=dimensions,
    )
    return evidence, draft, script
