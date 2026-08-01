"""Read models for UI-046 — the queries behind the command center's panels.

Kept out of the endpoint module because two of these carry real rules rather than
plain serialization:

* `build_summary` computes Section 4.3's reconciliation server-side. The contract
  requires the UI to show "Status data delayed" rather than a total it cannot
  justify, which is only possible if the server says whether the numbers add up.

* `build_item_detail` decides what evidence is safe to return. Metadata yes,
  content no — a captured network payload can contain request headers, so it is
  reported as an entry count with an artifact reference for an authenticated,
  masked download (Section 14.14).
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_suite import AutomationSuiteSnapshot
from app.models.execution import ExecutionRun
from app.models.execution_command_center import (
    TERMINAL_RUN_STATES,
    ExecutionRunAssertion,
    ExecutionRunEvidence,
    ExecutionRunItem,
    ExecutionRunItemStep,
)
from app.models.user import User
from app.services.execution_command_center import events, outcomes

# Section 3.1 — computed on the server so the UI cannot drift from the state
# machine about which action is primary.
PRIMARY_ACTION_BY_STATE = {
    "READINESS_PENDING": "VIEW_READINESS",
    "BLOCKED_BEFORE_START": "REVIEW_BLOCKER",
    "QUEUED": "VIEW_QUEUE_POSITION",
    "RUNNING": "PAUSE_AFTER_CURRENT",
    "PAUSE_REQUESTED": "VIEW_PAUSE_PROGRESS",
    "PAUSED": "RESUME",
    "STOP_REQUESTED": "VIEW_STOP_PROGRESS",
    "STOPPED": "OPEN_REPORT",
    "CANCELLED": "OPEN_REPORT",
    "COMPLETED": "OPEN_REPORT",
}

_ACTIVE_LIFECYCLE = ("STARTING", "RUNNING", "PAUSED")

_COUNT_KEY_BY_RESULT = {
    "PASS": "passed",
    "FAIL": "failed",
    "INCONCLUSIVE": "inconclusive",
    "BLOCKED": "blocked",
    "ENVIRONMENT_FAILURE": "environment_failure",
    "DATA_FAILURE": "data_failure",
    "AUTOMATION_FAILURE": "automation_failure",
    "POLICY_BLOCKED": "policy_blocked",
    "SKIPPED": "skipped",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def primary_action(run: ExecutionRun) -> str:
    return PRIMARY_ACTION_BY_STATE.get(run.lifecycle_state or "", "VIEW_READINESS")


def is_terminal(run: ExecutionRun) -> bool:
    return (run.lifecycle_state or "") in TERMINAL_RUN_STATES


async def build_identity(
    db: AsyncSession, run: ExecutionRun, *, can_control: bool, can_cancel: bool
) -> dict:
    snapshot = None
    if run.suite_snapshot_id is not None:
        snapshot = await db.get(AutomationSuiteSnapshot, run.suite_snapshot_id)

    triggered_by_name = None
    if run.triggered_by is not None:
        user = await db.get(User, run.triggered_by)
        triggered_by_name = getattr(user, "full_name", None) if user else None

    frameworks = sorted(
        {
            f
            for f in (
                await db.execute(
                    select(ExecutionRunItem.framework).where(
                        ExecutionRunItem.execution_run_id == run.id
                    )
                )
            ).scalars().all()
            if f
        }
    )

    return {
        "id": run.id,
        "execution_id": run.execution_id,
        "project_id": run.project_id,
        "suite_id": run.suite_id,
        "suite_name": run.suite_name,
        "suite_snapshot_id": run.suite_snapshot_id,
        "suite_version": (snapshot.suite_version if snapshot else None),
        "snapshot_checksum": (snapshot.checksum if snapshot else None),
        "environment": run.environment,
        "execution_purpose": run.execution_purpose,
        "frameworks": frameworks,
        "trigger_source": run.trigger_source,
        "triggered_by": run.triggered_by,
        "triggered_by_name": triggered_by_name,
        "lifecycle_state": run.lifecycle_state,
        "outcome": run.outcome,
        "run_version": run.run_version or 0,
        "pending_command": run.pending_command,
        "correlation_id": run.correlation_id,
        "parallel_limit": run.parallel_limit or 1,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "readiness": run.readiness,
        "primary_action": primary_action(run),
        "is_terminal": is_terminal(run),
        "latest_sequence": run.event_sequence or 0,
        "can_control": can_control,
        "can_cancel": can_cancel,
    }


async def list_suite_runs(db: AsyncSession, suite_id: int, *, limit: int) -> list[dict]:
    """Thin projection of a suite's runs, newest first."""
    runs = (
        await db.execute(
            select(ExecutionRun)
            .where(ExecutionRun.suite_id == suite_id)
            .order_by(ExecutionRun.id.desc())
            .limit(limit)
        )
    ).scalars().all()

    return [
        {
            "id": run.id,
            "execution_id": run.execution_id,
            "lifecycle_state": run.lifecycle_state,
            "outcome": run.outcome,
            "environment": run.environment,
            "execution_purpose": run.execution_purpose,
            "total_tests": run.total_tests or 0,
            "passed": run.passed or 0,
            "failed": run.failed or 0,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "is_terminal": is_terminal(run),
        }
        for run in runs
    ]


async def build_summary(db: AsyncSession, run: ExecutionRun) -> dict:
    """Section 4 — the status strip, with an explicit reconciliation verdict."""
    rows = (
        await db.execute(
            select(
                ExecutionRunItem.result,
                ExecutionRunItem.lifecycle_state,
                func.count().label("n"),
            )
            .where(ExecutionRunItem.execution_run_id == run.id)
            .group_by(ExecutionRunItem.result, ExecutionRunItem.lifecycle_state)
        )
    ).all()

    counts = {key: 0 for key in _COUNT_KEY_BY_RESULT.values()}
    counts["running"] = 0
    counts["queued"] = 0
    total = 0
    finalized = 0

    for result, lifecycle, n in rows:
        total += n
        if lifecycle == "COMPLETED":
            key = _COUNT_KEY_BY_RESULT.get(result)
            if key is not None:
                counts[key] += n
                finalized += n
            else:
                # A COMPLETED item still marked PENDING is a real inconsistency;
                # it is counted nowhere and surfaces via the reconciliation flag
                # rather than being quietly folded into a bucket.
                pass
        elif lifecycle in _ACTIVE_LIFECYCLE:
            counts["running"] += n
        else:
            counts["queued"] += n

    accounted = finalized + counts["running"] + counts["queued"]
    reconciled = accounted == total
    detail = (
        None
        if reconciled
        else (
            f"{total - accounted} item(s) are in a state the summary cannot "
            "classify. Counts are shown as delayed rather than as a total that "
            "does not add up."
        )
    )

    evidence_ready = (run.readiness or {}).get("axes", {}).get("environment", False)

    return {
        "total": total,
        "completed": finalized,
        "completion_percent": (round(finalized / total * 100, 1) if total else 0.0),
        "counts": counts,
        "reconciled": reconciled,
        "reconciliation_detail": detail,
        # Sequential in this slice, so "in use" is whatever is actually running.
        "parallel_in_use": counts["running"],
        "parallel_allowed": run.parallel_limit or 1,
        "queue_depth": counts["queued"],
        "evidence_captured": run.evidence_captured_total or 0,
        "evidence_required": run.evidence_required_total or 0,
        "environment_ready": bool(evidence_ready),
        "operational_message": _operational_message(run, counts, total, finalized),
    }


def _operational_message(
    run: ExecutionRun, counts: dict[str, int], total: int, finalized: int
) -> str:
    """Plain English, per Section 4.1. No jargon, no invented urgency."""
    state = run.lifecycle_state or ""
    if state == "BLOCKED_BEFORE_START":
        blockers = (run.readiness or {}).get("blockers") or []
        return (
            f"This run cannot start: {len(blockers)} readiness check(s) failed. "
            "Nothing has been dispatched."
        )
    if state == "READINESS_PENDING":
        return "Evaluating readiness before dispatching any test case."
    if state == "QUEUED":
        return f"{total} test case(s) queued. Waiting for a worker to begin."
    if state == "PAUSE_REQUESTED":
        return (
            "Pause requested. The test currently in flight will finish before "
            "dispatch stops."
        )
    if state == "PAUSED":
        return f"Paused with {counts['queued']} test case(s) still queued."
    if state == "STOP_REQUESTED":
        return "Stop requested. Finalizing available results and evidence."
    if state == "CANCELLED":
        return "Cancelled. Partial evidence captured before cancellation is retained."
    if state in ("STOPPED", "COMPLETED"):
        needing = (
            counts["failed"]
            + counts["inconclusive"]
            + counts["blocked"]
            + counts["environment_failure"]
            + counts["data_failure"]
            + counts["automation_failure"]
            + counts["policy_blocked"]
        )
        if needing:
            return (
                f"Run finished as {run.outcome}. {needing} test case(s) need attention."
            )
        return f"Run finished as {run.outcome}."
    attention = counts["failed"] + counts["inconclusive"]
    if attention:
        return (
            f"Executing test case {finalized + 1} of {total}. {attention} result(s) "
            "need attention; execution continues."
        )
    return f"Executing test case {min(finalized + 1, total)} of {total}."


async def list_items(
    db: AsyncSession,
    run: ExecutionRun,
    *,
    cursor: int = 0,
    limit: int = 100,
    results: list[str] | None = None,
    lifecycle_states: list[str] | None = None,
    search: str | None = None,
    journey: str | None = None,
    framework: str | None = None,
    priority: str | None = None,
) -> dict:
    """Cursor-paginated matrix rows, filtered.

    Ordered by `order_index`, which is also the cursor — the suite execution
    sequence is stable and unique per run, so it is a correct cursor as well as
    the order Section 6.2 requires "Reset order" to return to.
    """
    filters = [ExecutionRunItem.execution_run_id == run.id]
    if results:
        filters.append(ExecutionRunItem.result.in_(results))
    if lifecycle_states:
        filters.append(ExecutionRunItem.lifecycle_state.in_(lifecycle_states))
    if journey:
        filters.append(ExecutionRunItem.journey == journey)
    if framework:
        filters.append(func.lower(ExecutionRunItem.framework) == framework.lower())
    if priority:
        filters.append(func.lower(ExecutionRunItem.priority) == priority.lower())
    if search:
        needle = f"%{search.lower()}%"
        # Section 5.1: search covers id, objective and error text.
        filters.append(
            func.lower(func.coalesce(ExecutionRunItem.test_case_key, ""))
            .like(needle)
            | func.lower(func.coalesce(ExecutionRunItem.title, "")).like(needle)
            | func.lower(func.coalesce(ExecutionRunItem.attention_reason, "")).like(needle)
            | func.lower(func.coalesce(ExecutionRunItem.error_message, "")).like(needle)
        )

    total_matching = (
        await db.execute(select(func.count()).select_from(ExecutionRunItem).where(*filters))
    ).scalar_one()

    page = (
        await db.execute(
            select(ExecutionRunItem)
            .where(*filters, ExecutionRunItem.order_index > cursor)
            .order_by(ExecutionRunItem.order_index)
            .limit(limit + 1)
        )
    ).scalars().all()

    has_more = len(page) > limit
    page = page[:limit]
    return {
        "items": page,
        "next_cursor": (page[-1].order_index if has_more and page else None),
        "total_matching": total_matching,
    }


async def suite_tree(db: AsyncSession, run: ExecutionRun) -> list[dict]:
    """Section 5.2 — journey nodes with live progress and worst active status.

    Grouped by journey then framework. Built from the items themselves rather than
    from the suite, so the tree describes what is executing rather than what the
    suite currently contains.
    """
    rows = (
        await db.execute(
            select(
                ExecutionRunItem.journey,
                ExecutionRunItem.framework,
                ExecutionRunItem.lifecycle_state,
                ExecutionRunItem.result,
                func.count().label("n"),
            )
            .where(ExecutionRunItem.execution_run_id == run.id)
            .group_by(
                ExecutionRunItem.journey,
                ExecutionRunItem.framework,
                ExecutionRunItem.lifecycle_state,
                ExecutionRunItem.result,
            )
        )
    ).all()

    tree: dict[str, dict] = {}
    for journey, framework, lifecycle, result, n in rows:
        journey_key = journey or "Ungrouped"
        node = tree.setdefault(
            journey_key,
            {"journey": journey_key, "total": 0, "complete": 0, "worst": None, "children": {}},
        )
        child_key = framework or "Unspecified"
        child = node["children"].setdefault(
            child_key, {"framework": child_key, "total": 0, "complete": 0}
        )
        node["total"] += n
        child["total"] += n
        if lifecycle == "COMPLETED":
            node["complete"] += n
            child["complete"] += n
            node["worst"] = _worse_of(node["worst"], result)

    return [
        {
            "journey": node["journey"],
            "total": node["total"],
            "complete": node["complete"],
            "worst_result": node["worst"],
            "children": sorted(node["children"].values(), key=lambda c: c["framework"]),
        }
        for node in sorted(tree.values(), key=lambda n: n["journey"])
    ]


_SEVERITY_ORDER = (
    "POLICY_BLOCKED",
    "ENVIRONMENT_FAILURE",
    "DATA_FAILURE",
    "AUTOMATION_FAILURE",
    "BLOCKED",
    "FAIL",
    "INCONCLUSIVE",
    "SKIPPED",
    "PASS",
)


def _worse_of(current: str | None, candidate: str | None) -> str | None:
    """Reuses the same severity order as the run rollup, so a tree node's worst
    status can never disagree with the run outcome about which is worse."""
    if candidate is None:
        return current
    if current is None:
        return candidate
    order = {name: i for i, name in enumerate(_SEVERITY_ORDER)}
    return min(current, candidate, key=lambda r: order.get(r, len(_SEVERITY_ORDER)))


async def build_item_detail(db: AsyncSession, item: ExecutionRunItem) -> dict:
    steps = (
        await db.execute(
            select(ExecutionRunItemStep)
            .where(ExecutionRunItemStep.execution_run_item_id == item.id)
            .order_by(ExecutionRunItemStep.step_number)
        )
    ).scalars().all()
    assertions = (
        await db.execute(
            select(ExecutionRunAssertion).where(
                ExecutionRunAssertion.execution_run_item_id == item.id
            )
        )
    ).scalars().all()
    evidence = (
        await db.execute(
            select(ExecutionRunEvidence)
            .where(ExecutionRunEvidence.execution_run_item_id == item.id)
            .order_by(ExecutionRunEvidence.id)
        )
    ).scalars().all()

    quorum = outcomes.evidence_quorum(
        [
            outcomes.EvidenceFact(e.evidence_type, e.mandatory, e.status)
            for e in evidence
        ]
    )

    current_step = next((s for s in steps if s.status == "running"), None)
    if current_step is None:
        completed = [s for s in steps if s.status != "pending"]
        current_step = completed[-1] if completed else None

    screenshots = [
        e
        for e in evidence
        if e.evidence_type == "screenshot" and e.status == "captured"
    ]
    latest_screenshot = screenshots[-1] if screenshots else None

    return {
        "item": item,
        "script_id": item.script_id,
        "test_case_version": item.test_case_version,
        "environment": item.environment,
        "session_id": item.session_id,
        "retry_reason": item.retry_reason,
        "error_message": item.error_message,
        "snapshot_member": item.snapshot_member or {},
        "current_step": current_step,
        "steps": steps,
        "assertions": assertions,
        "evidence": [_evidence_out(e) for e in evidence],
        "quorum_met": quorum.met,
        "quorum_missing": list(quorum.missing),
        "latest_screenshot_evidence_id": (latest_screenshot.id if latest_screenshot else None),
        "latest_screenshot_captured_at": (
            latest_screenshot.captured_at if latest_screenshot else None
        ),
    }


def _evidence_out(row: ExecutionRunEvidence) -> dict:
    """Metadata only. A payload's entries can carry request headers, so the count
    is returned and the content is left to the masked download endpoint at
    `GET /runs/{run_id}/evidence/{evidence_id}`."""
    entries = None
    if isinstance(row.payload, dict):
        value = row.payload.get("entries")
        if isinstance(value, list):
            entries = len(value)
    return {
        "id": row.id,
        "evidence_type": row.evidence_type,
        "status": row.status,
        "mandatory": row.mandatory,
        "summary": row.summary,
        "payload_entry_count": entries,
        "size_bytes": row.size_bytes,
        "has_artifact": bool(row.file_path),
        "sanitized": row.sanitized,
        "redaction_state": row.redaction_state,
        "checksum_sha256": row.checksum_sha256,
        "content_type": row.content_type,
        # Whether the viewer should offer a download at all. A row with no
        # artifact and no payload has nothing behind the link.
        "downloadable": row.status == "captured"
        and bool(row.file_path or row.payload is not None),
        "unavailable_reason": row.unavailable_reason,
        "captured_at": row.captured_at,
    }


async def build_event_page(
    db: AsyncSession, run: ExecutionRun, *, after: int, limit: int
) -> dict:
    rows = await events.read_after(db, run.id, after=after, limit=limit + 1)
    has_more = len(rows) > limit
    rows = rows[:limit]
    latest = run.event_sequence or 0
    newest_age = None
    if rows:
        newest_age = (_now() - rows[-1].occurred_at).total_seconds()
    return {
        "events": rows,
        "latest_sequence": latest,
        "newest_event_age_seconds": newest_age,
        "has_more": has_more,
    }
