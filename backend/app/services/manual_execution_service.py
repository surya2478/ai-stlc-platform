"""Manual Execution service.

Step-level execution recorded by a human tester. Replaces the previous
localStorage-only path with real persistence: every status change, comment,
actual result, and evidence file lands in the database / object store and is
served back through authenticated routes.
"""
from __future__ import annotations

import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import aiofiles
from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.defect import DefectDraft
from app.models.execution import ExecutionResult, ExecutionRun, ManualStepResult
from app.models.test_case import TestCase
from app.models.test_data import TestDataRecord
from app.services.display_id_service import display_id, temporary_id
from app.services.parameter_binding import substitute_step

settings = get_settings()

MAX_EVIDENCE_BYTES = settings.max_upload_size_mb * 1024 * 1024
EVIDENCE_CHUNK = 1024 * 1024
_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")

# Statuses that count as "executed" for run-roll-up
_TERMINAL_STATUSES = {"passed", "failed", "blocked", "skipped"}


def _sanitize(name: str | None) -> str:
    raw = Path(name or "evidence").name
    safe = _SAFE_NAME.sub("_", raw).strip("._")
    return safe or "evidence"


def _evidence_root(project_id: int, run_id: int) -> Path:
    return Path(settings.file_storage_path) / "manual_evidence" / str(project_id) / str(run_id)


def _evidence_to_out(items: Iterable[dict]) -> list[dict]:
    """Decorate stored evidence descriptors with a download_url for the API layer."""
    out: list[dict] = []
    for ev in items or []:
        ev_id = ev.get("id")
        if not ev_id:
            continue
        out.append({
            "id": ev_id,
            "filename": ev.get("filename") or "evidence",
            "size": int(ev.get("size") or 0),
            "content_type": ev.get("content_type"),
            "uploaded_at": ev.get("uploaded_at"),
            "download_url": f"/api/v1/execution/manual/evidence/{ev_id}",
        })
    return out


# ── Read helpers ─────────────────────────────────────────────────────────────


async def get_step(db: AsyncSession, step_id: int) -> ManualStepResult | None:
    res = await db.execute(select(ManualStepResult).where(ManualStepResult.id == step_id))
    return res.scalar_one_or_none()


async def get_step_with_run(
    db: AsyncSession, step_id: int
) -> tuple[ManualStepResult, ExecutionResult, ExecutionRun] | None:
    """Return the step plus its parent result and run, or None if missing."""
    step = await get_step(db, step_id)
    if not step:
        return None
    result = await db.get(ExecutionResult, step.execution_result_id)
    if not result:
        return None
    run = await db.get(ExecutionRun, result.execution_run_id)
    if not run:
        return None
    return step, result, run


async def list_steps_for_result(
    db: AsyncSession, execution_result_id: int
) -> list[ManualStepResult]:
    res = await db.execute(
        select(ManualStepResult)
        .where(ManualStepResult.execution_result_id == execution_result_id)
        .order_by(ManualStepResult.step_number.asc())
    )
    return list(res.scalars().all())


async def get_result_with_run(
    db: AsyncSession, result_id: int
) -> tuple[ExecutionResult, ExecutionRun] | None:
    """Return the ExecutionResult plus its parent run, or None if missing."""
    result = await db.get(ExecutionResult, result_id)
    if not result:
        return None
    run = await db.get(ExecutionRun, result.execution_run_id)
    if not run:
        return None
    return result, run


async def load_manual_run(db: AsyncSession, run_id: int) -> ExecutionRun | None:
    res = await db.execute(
        select(ExecutionRun)
        .where(ExecutionRun.id == run_id)
        .options(
            selectinload(ExecutionRun.results).selectinload(ExecutionResult.manual_steps),
            selectinload(ExecutionRun.results).selectinload(ExecutionResult.tested_by),
            selectinload(ExecutionRun.results).selectinload(ExecutionResult.blocking_defect),
        )
    )
    return res.scalar_one_or_none()


# ── Mutations ────────────────────────────────────────────────────────────────


async def start_manual_run(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    test_case_ids: list[int],
    environment: str | None,
    suite_name: str | None,
    bound_data_records: dict[int, int] | None = None,
) -> ExecutionRun:
    """Create an ExecutionRun (manual), one ExecutionResult per test case, and a
    ManualStepResult per step.

    Test cases without structured steps still get an ExecutionResult so the
    tester can record a single overall outcome.

    If `bound_data_records` maps test_case_id -> TestDataRecord.id, the matching
    record's payload is substituted into step text at start time. The original
    test case text is left untouched; the substituted snapshot lives on the
    ManualStepResult row.
    """
    if not test_case_ids:
        raise HTTPException(status_code=422, detail="At least one test case is required")

    tc_rows = await db.execute(
        select(TestCase).where(
            TestCase.id.in_(test_case_ids), TestCase.project_id == project_id
        )
    )
    test_cases: list[TestCase] = list(tc_rows.scalars().all())
    if len(test_cases) != len(set(test_case_ids)):
        raise HTTPException(
            status_code=403,
            detail="One or more test cases do not belong to this project",
        )

    # Preload bound TestDataRecord payloads (project-scoped for safety).
    bound_records: dict[int, dict] = {}
    binding_meta: dict[int, dict] = {}  # test_case_id -> {"record_id": ..., "record_key": ...}
    binding_input = bound_data_records or {}
    if binding_input:
        record_ids = list({int(rid) for rid in binding_input.values() if rid})
        if record_ids:
            rec_rows = await db.execute(
                select(TestDataRecord).where(
                    TestDataRecord.id.in_(record_ids),
                    TestDataRecord.project_id == project_id,
                )
            )
            records_by_id = {r.id: r for r in rec_rows.scalars().all()}
            if len(records_by_id) != len(record_ids):
                raise HTTPException(
                    status_code=403,
                    detail="One or more bound test data records do not belong to this project.",
                )
            for tc_id_str, rec_id in binding_input.items():
                tc_id = int(tc_id_str)
                rec = records_by_id.get(int(rec_id))
                if not rec:
                    continue
                payload = rec.masked_payload_json or rec.payload_json or {}
                if isinstance(payload, dict):
                    bound_records[tc_id] = payload
                    binding_meta[tc_id] = {
                        "record_id": rec.id,
                        "data_set_id": rec.data_set_id,
                        "record_key": rec.record_key,
                    }

    run = ExecutionRun(
        project_id=project_id,
        created_by=user_id,
        execution_id=temporary_id("ER"),
        suite_name=suite_name,
        environment=environment,
        # Constrained by ck_execution_runs_status (migration 017):
        # pending | queued | running | completed | failed | cancelled
        status="running",
        execution_type="manual",
        source_type="manual",
        metadata_={"source_type": "manual"},
        total_tests=len(test_cases),
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)
    await db.flush()

    for tc in test_cases:
        record = bound_records.get(tc.id)
        binding = binding_meta.get(tc.id)
        exec_result = ExecutionResult(
            execution_run_id=run.id,
            test_case_id=tc.id,
            project_id=project_id,
            test_name=tc.title,
            # Constrained by ck_execution_results_status (migration 017):
            # pending | pass | fail | skip | error | blocked | not_run | running
            status="running",
            metadata_={"bound_data_record": binding} if binding else None,
        )
        db.add(exec_result)
        await db.flush()

        steps = tc.steps or []
        for step in steps:
            step_number = int(step.get("step_number") or 0)
            if step_number <= 0:
                continue
            raw_action = str(step.get("action") or "")[:5000] or None
            raw_expected = str(step.get("expected_result") or "")[:5000] or None
            resolved = substitute_step(action=raw_action, expected=raw_expected, record=record)
            db.add(
                ManualStepResult(
                    execution_result_id=exec_result.id,
                    project_id=project_id,
                    step_number=step_number,
                    action_text=resolved["action_text"],
                    expected_text=resolved["expected_text"],
                    status="not_run",
                    updated_by=user_id,
                )
            )
        await db.flush()

    return run


async def update_step(
    db: AsyncSession,
    step: ManualStepResult,
    *,
    user_id: int,
    status_value: str | None,
    actual_result: str | None,
    comments: str | None,
) -> ManualStepResult:
    now = datetime.now(timezone.utc)
    changed = False

    if actual_result is not None:
        step.actual_result = actual_result
        changed = True
    if comments is not None:
        step.comments = comments
        changed = True

    if status_value is not None and status_value != step.status:
        if status_value not in {"not_run", "in_progress", "passed", "failed", "blocked", "skipped"}:
            raise HTTPException(status_code=422, detail=f"Invalid step status: {status_value}")
        # Stamp started_at the first time we leave not_run
        if step.status == "not_run" and status_value != "not_run" and step.started_at is None:
            step.started_at = now
        if status_value in _TERMINAL_STATUSES:
            step.completed_at = now
        else:
            step.completed_at = None
        step.status = status_value
        changed = True

    if changed:
        step.updated_by = user_id
        await db.flush()

    return step


async def update_result_uat_fields(
    db: AsyncSession,
    result: ExecutionResult,
    *,
    user_id: int,
    status: str | None,
    tested_by_id: int | None,
    sit_status: str | None,
    blocking_defect_id: int | None,
    other_reason: str | None,
) -> ExecutionResult:
    """Apply the UAT template's per-result tracking fields: Overall Status
    outcome, Tested By (defaults to the acting user when not explicitly
    provided), SIT status, and Blocking Snag ID / Other Reason."""
    if status is not None:
        result.status = status
    result.tested_by_id = tested_by_id if tested_by_id is not None else user_id
    if sit_status is not None:
        result.sit_status = sit_status
    if blocking_defect_id is not None:
        defect = await db.get(DefectDraft, blocking_defect_id)
        if defect is None or defect.project_id != result.project_id:
            raise HTTPException(status_code=422, detail="Defect not found in this project")
        result.blocking_defect_id = blocking_defect_id
    if other_reason is not None:
        result.other_reason = other_reason
    await db.flush()
    return result


# ── Evidence ─────────────────────────────────────────────────────────────────


async def attach_evidence(
    db: AsyncSession,
    *,
    step: ManualStepResult,
    run: ExecutionRun,
    user_id: int,
    file: UploadFile,
) -> dict:
    """Stream an evidence file to disk and append a descriptor to the step."""
    safe_name = _sanitize(file.filename)
    storage_dir = _evidence_root(step.project_id, run.id) / str(step.execution_result_id) / str(step.step_number)
    storage_dir.mkdir(parents=True, exist_ok=True)

    evidence_id = uuid.uuid4().hex
    stored_name = f"{evidence_id}_{safe_name}"
    file_path = storage_dir / stored_name

    size = 0
    first_chunk = await file.read(EVIDENCE_CHUNK)
    if not first_chunk:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")

    try:
        async with aiofiles.open(file_path, "wb") as fh:
            chunk = first_chunk
            while chunk:
                size += len(chunk)
                if size > MAX_EVIDENCE_BYTES:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"Evidence exceeds {settings.max_upload_size_mb} MB limit",
                    )
                await fh.write(chunk)
                chunk = await file.read(EVIDENCE_CHUNK)
    except HTTPException:
        raise
    except Exception:
        try:
            os.remove(file_path)
        except OSError:
            pass
        raise

    descriptor = {
        "id": evidence_id,
        "filename": safe_name,
        "stored_filename": stored_name,
        "file_path": str(file_path),
        "size": size,
        "content_type": file.content_type,
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "uploaded_by": user_id,
    }
    existing = list(step.evidence or [])
    existing.append(descriptor)
    step.evidence = existing
    step.updated_by = user_id
    await db.flush()
    return descriptor


async def find_evidence(
    db: AsyncSession, evidence_id: str
) -> tuple[ManualStepResult, dict] | None:
    """Return the step and the matching evidence descriptor, or None.

    Note: this scans steps that have *any* evidence and then filters in Python.
    With a manageable run size this is fine; if it ever becomes hot we can add a
    dedicated evidence table.
    """
    rows = await db.execute(
        select(ManualStepResult).where(ManualStepResult.evidence.isnot(None))
    )
    for step in rows.scalars().all():
        for ev in step.evidence or []:
            if ev.get("id") == evidence_id:
                return step, ev
    return None


async def detach_evidence(db: AsyncSession, step: ManualStepResult, evidence_id: str) -> bool:
    items = list(step.evidence or [])
    new_items = [ev for ev in items if ev.get("id") != evidence_id]
    if len(new_items) == len(items):
        return False
    # Remove the file from disk best-effort
    removed = next((ev for ev in items if ev.get("id") == evidence_id), None)
    if removed and removed.get("file_path"):
        try:
            os.remove(removed["file_path"])
        except OSError:
            pass
    step.evidence = new_items
    await db.flush()
    return True


# ── Roll-up ──────────────────────────────────────────────────────────────────


# ManualStepResult uses our own vocabulary (passed/failed/blocked/skipped/...).
# ExecutionResult.status is bound by ck_execution_results_status to:
#   pending | pass | fail | skip | error | blocked | not_run | running
# Map at the boundary when rolling up.
_STEP_TO_RESULT_STATUS = {
    "passed": "pass",
    "failed": "fail",
    "skipped": "skip",
    "blocked": "blocked",
    "not_run": "not_run",
    "in_progress": "running",
}


def _roll_up_result_status(step_statuses: list[str]) -> str:
    """Convert per-step statuses to a single ExecutionResult.status value.

    Rules (in priority order):
      - any failed     → fail
      - any blocked    → blocked
      - any in_progress/not_run → running
      - all skipped    → skip
      - all passed (or passed+skipped) → pass
    """
    if not step_statuses:
        return "running"
    s = set(step_statuses)
    if "failed" in s:
        return "fail"
    if "blocked" in s:
        return "blocked"
    if "in_progress" in s or "not_run" in s:
        return "running"
    if s == {"skipped"}:
        return "skip"
    if s <= {"passed", "skipped"}:
        return "pass"
    return "running"


async def complete_run(
    db: AsyncSession, run: ExecutionRun, *, user_id: int
) -> ExecutionRun:
    """Finalise per-result statuses, compute run totals, and mark the run completed."""
    fresh = await load_manual_run(db, run.id)
    if not fresh:
        raise HTTPException(status_code=404, detail="Execution run not found")

    now = datetime.now(timezone.utc)
    passed = failed = skipped = 0
    for result in fresh.results:
        step_statuses = [step.status for step in result.manual_steps]
        # If the test case has no structured steps, fall back to the current
        # result.status. Translate any leftover step-vocab values to result-vocab.
        if step_statuses:
            derived = _roll_up_result_status(step_statuses)
        else:
            current = result.status or "running"
            derived = _STEP_TO_RESULT_STATUS.get(current, current)
        # When finalising, anything still in flight rolls to skip
        if derived in {"running", "not_run", "pending"}:
            derived = "skip"
        result.status = derived
        if derived == "pass":
            passed += 1
        elif derived == "fail":
            failed += 1
        else:
            skipped += 1

    fresh.passed = passed
    fresh.failed = failed
    fresh.skipped = skipped
    fresh.total_tests = len(fresh.results)
    fresh.status = "completed"
    fresh.metadata_ = {**(fresh.metadata_ or {}), "completed_at": now.isoformat(), "completed_by": user_id}
    await db.flush()
    return fresh


# ── Serialisation helper ─────────────────────────────────────────────────────


def serialize_step(step: ManualStepResult) -> dict:
    """Build a payload that satisfies ManualStepResultOut. Evidence descriptors are
    decorated with a per-item download URL pointing at the authenticated route.
    """
    return {
        "id": step.id,
        "execution_result_id": step.execution_result_id,
        "step_number": step.step_number,
        "action_text": step.action_text,
        "expected_text": step.expected_text,
        "status": step.status,
        "actual_result": step.actual_result,
        "comments": step.comments,
        "evidence": _evidence_to_out(step.evidence or []),
        "started_at": step.started_at,
        "completed_at": step.completed_at,
        "updated_by": step.updated_by,
        "updated_at": step.updated_at,
    }
