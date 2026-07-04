"""Execution Dashboard aggregation service.

Powers GET /execution/dashboard. Returns a unified view across Manual,
Automation, and AI execution flows. All counts come from `execution_runs` +
`execution_results` so a single run is never double-counted.

Filters supported:
    - project_id (required)
    - environment (optional, single value)
    - date_from / date_to (optional, inclusive — applied to started_at;
      falls back to created_at when started_at is NULL)
    - execution_type (optional, one of manual|automation|ai)
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.defect import DefectDraft
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.test_case import TestCase
from app.models.user import User


_RUN_PASSED_STATES = {"completed", "auto_completed"}
_RUN_IN_PROGRESS_STATES = {"pending", "queued", "running"}
_RUN_FAILED_STATES = {"failed"}
_RUN_CANCELLED_STATES = {"cancelled"}
_RUN_REVIEW_STATES = {"review_required"}

# Result-level outcomes (per-test-case)
_RESULT_PASSED = {"pass", "passed"}
_RESULT_FAILED = {"fail", "failed", "error"}
_RESULT_BLOCKED = {"blocked"}
_RESULT_SKIPPED = {"skip", "skipped"}
_RESULT_IN_PROGRESS = {"running", "in_progress", "pending"}


def _coerce_dt(d: date | datetime | None) -> datetime | None:
    if d is None:
        return None
    if isinstance(d, datetime):
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    return datetime.combine(d, datetime.min.time(), tzinfo=timezone.utc)


def _run_started_or_created():
    """SQL expression: COALESCE(started_at, created_at)."""
    return func.coalesce(ExecutionRun.started_at, ExecutionRun.created_at)


def _apply_run_filters(stmt, *, project_id: int, environment: str | None,
                        date_from: datetime | None, date_to: datetime | None,
                        execution_type: str | None):
    stmt = stmt.where(ExecutionRun.project_id == project_id)
    if environment:
        stmt = stmt.where(ExecutionRun.environment == environment)
    if execution_type:
        stmt = stmt.where(ExecutionRun.execution_type == execution_type)
    if date_from is not None:
        stmt = stmt.where(_run_started_or_created() >= date_from)
    if date_to is not None:
        # date_to is inclusive end-of-day
        stmt = stmt.where(_run_started_or_created() < date_to + timedelta(days=1))
    return stmt


async def dashboard_payload(
    db: AsyncSession,
    *,
    project_id: int,
    environment: str | None = None,
    execution_type: str | None = None,
    date_from: date | datetime | None = None,
    date_to: date | datetime | None = None,
) -> dict[str, Any]:
    """Build the full dashboard payload in a small number of queries."""
    df = _coerce_dt(date_from)
    dt = _coerce_dt(date_to)

    # ─── 1. KPI counts at the run level (total / in-progress) ───────────────
    run_status_stmt = _apply_run_filters(
        select(ExecutionRun.status, func.count(ExecutionRun.id)).group_by(ExecutionRun.status),
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=execution_type,
    )
    run_status_rows = (await db.execute(run_status_stmt)).all()
    run_status_counts: dict[str, int] = {row[0]: int(row[1] or 0) for row in run_status_rows}

    total_runs = sum(run_status_counts.values())
    in_progress_runs = sum(v for k, v in run_status_counts.items() if k in _RUN_IN_PROGRESS_STATES)
    review_required_runs = sum(v for k, v in run_status_counts.items() if k in _RUN_REVIEW_STATES)

    # ─── 2. Total-test, passed/failed/skipped + duration totals from runs ────
    totals_stmt = _apply_run_filters(
        select(
            func.coalesce(func.sum(ExecutionRun.total_tests), 0),
            func.coalesce(func.sum(ExecutionRun.passed), 0),
            func.coalesce(func.sum(ExecutionRun.failed), 0),
            func.coalesce(func.sum(ExecutionRun.skipped), 0),
            func.coalesce(func.avg(ExecutionRun.duration_seconds), 0.0),
            func.coalesce(func.sum(ExecutionRun.duration_seconds), 0.0),
        ),
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=execution_type,
    )
    totals_row = (await db.execute(totals_stmt)).one()
    total_tests, passed_results, failed_results, skipped_results, avg_seconds, total_seconds = totals_row

    # ─── 3. Blocked count from execution_results (runs don't carry blocked) ──
    blocked_stmt = (
        select(func.count(ExecutionResult.id))
        .join(ExecutionRun, ExecutionRun.id == ExecutionResult.execution_run_id)
        .where(ExecutionResult.project_id == project_id)
        .where(ExecutionResult.status.in_(list(_RESULT_BLOCKED)))
    )
    blocked_stmt = _apply_run_filters(
        blocked_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=execution_type,
    )
    blocked_results = int((await db.execute(blocked_stmt)).scalar_one() or 0)

    # ─── 4. By execution_type breakdown ──────────────────────────────────────
    type_stmt = (
        select(
            ExecutionRun.execution_type,
            func.count(ExecutionRun.id),
            func.coalesce(func.sum(ExecutionRun.total_tests), 0),
            func.coalesce(func.sum(ExecutionRun.passed), 0),
            func.coalesce(func.sum(ExecutionRun.failed), 0),
            func.coalesce(func.sum(ExecutionRun.skipped), 0),
        )
        .group_by(ExecutionRun.execution_type)
    )
    type_stmt = _apply_run_filters(
        type_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=None,
    )
    type_rows = (await db.execute(type_stmt)).all()

    blocked_by_type_stmt = (
        select(ExecutionRun.execution_type, func.count(ExecutionResult.id))
        .join(ExecutionRun, ExecutionRun.id == ExecutionResult.execution_run_id)
        .where(ExecutionResult.status.in_(list(_RESULT_BLOCKED)))
        .group_by(ExecutionRun.execution_type)
    )
    blocked_by_type_stmt = _apply_run_filters(
        blocked_by_type_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=None,
    )
    blocked_by_type_rows = (await db.execute(blocked_by_type_stmt)).all()
    blocked_by_type: dict[str, int] = {row[0]: int(row[1] or 0) for row in blocked_by_type_rows}

    in_progress_by_type_stmt = (
        select(ExecutionRun.execution_type, func.count(ExecutionRun.id))
        .where(ExecutionRun.status.in_(list(_RUN_IN_PROGRESS_STATES)))
        .group_by(ExecutionRun.execution_type)
    )
    in_progress_by_type_stmt = _apply_run_filters(
        in_progress_by_type_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=None,
    )
    in_progress_by_type_rows = (await db.execute(in_progress_by_type_stmt)).all()
    in_progress_by_type: dict[str, int] = {row[0]: int(row[1] or 0) for row in in_progress_by_type_rows}

    by_type: list[dict[str, Any]] = []
    for execution_type_value, run_count, t_total, t_pass, t_fail, t_skip in type_rows:
        et_key = execution_type_value or "manual"
        blocked = blocked_by_type.get(et_key, 0)
        in_prog = in_progress_by_type.get(et_key, 0)
        executed = max(int(t_pass or 0) + int(t_fail or 0) + int(t_skip or 0) + blocked, 1)
        pass_rate = round((int(t_pass or 0) / executed) * 100, 1) if executed else 0.0
        by_type.append({
            "execution_type": et_key,
            "run_count": int(run_count or 0),
            "total_tests": int(t_total or 0),
            "passed": int(t_pass or 0),
            "failed": int(t_fail or 0),
            "skipped": int(t_skip or 0),
            "blocked": blocked,
            "in_progress": in_prog,
            "pass_rate": pass_rate,
        })

    # ─── 5. Trend series (daily counts per type) ─────────────────────────────
    day_expr = func.date_trunc("day", _run_started_or_created())
    trend_stmt = (
        select(
            day_expr.label("day"),
            ExecutionRun.execution_type,
            func.count(ExecutionRun.id),
        )
        .group_by("day", ExecutionRun.execution_type)
        .order_by("day")
    )
    trend_stmt = _apply_run_filters(
        trend_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=None,
    )
    trend_rows = (await db.execute(trend_stmt)).all()
    trend_by_day: dict[str, dict[str, int]] = defaultdict(lambda: {"manual": 0, "automation": 0, "ai": 0, "hybrid": 0})
    for day_value, type_value, count in trend_rows:
        if day_value is None:
            continue
        key = day_value.date().isoformat() if hasattr(day_value, "date") else str(day_value)
        trend_by_day[key][type_value or "manual"] = int(count or 0)
    trend = [
        {"date": d, **counts}
        for d, counts in sorted(trend_by_day.items())
    ]

    # ─── 6. By environment ───────────────────────────────────────────────────
    env_stmt = (
        select(
            func.coalesce(ExecutionRun.environment, "unknown"),
            func.count(ExecutionRun.id),
        )
        .group_by(ExecutionRun.environment)
    )
    env_stmt = _apply_run_filters(
        env_stmt,
        project_id=project_id, environment=None,  # don't filter by env when reporting env breakdown
        date_from=df, date_to=dt, execution_type=execution_type,
    )
    env_rows = (await db.execute(env_stmt)).all()
    by_environment = [{"environment": row[0], "run_count": int(row[1] or 0)} for row in env_rows]

    # ─── 7. By module (test_case.product) ────────────────────────────────────
    module_stmt = (
        select(
            func.coalesce(TestCase.product, "Unassigned").label("module"),
            func.count(ExecutionResult.id),
            func.sum(case((ExecutionResult.status.in_(list(_RESULT_FAILED)), 1), else_=0)),
        )
        .join(ExecutionRun, ExecutionRun.id == ExecutionResult.execution_run_id)
        .outerjoin(TestCase, TestCase.id == ExecutionResult.test_case_id)
        .group_by("module")
        .order_by(func.count(ExecutionResult.id).desc())
        .limit(8)
    )
    module_stmt = _apply_run_filters(
        module_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=execution_type,
    )
    module_rows = (await db.execute(module_stmt)).all()
    by_module = [
        {"module": row[0], "executions": int(row[1] or 0), "failures": int(row[2] or 0)}
        for row in module_rows
    ]

    # ─── 8. Recent runs (top 10 newest) ──────────────────────────────────────
    recent_stmt = (
        select(
            ExecutionRun,
            User.full_name,
        )
        .outerjoin(User, User.id == ExecutionRun.triggered_by)
        .order_by(_run_started_or_created().desc())
        .limit(10)
    )
    recent_stmt = _apply_run_filters(
        recent_stmt,
        project_id=project_id, environment=environment,
        date_from=df, date_to=dt, execution_type=execution_type,
    )
    recent_rows = (await db.execute(recent_stmt)).all()
    recent_runs = [
        {
            "id": row[0].id,
            "execution_id": row[0].execution_id,
            "execution_type": row[0].execution_type,
            "status": row[0].status,
            "environment": row[0].environment,
            "suite_name": row[0].suite_name,
            "total_tests": row[0].total_tests,
            "passed": row[0].passed,
            "failed": row[0].failed,
            "started_at": (row[0].started_at or row[0].created_at).isoformat() if (row[0].started_at or row[0].created_at) else None,
            "duration_seconds": row[0].duration_seconds,
            "triggered_by_name": row[1],
            "confidence_score": row[0].confidence_score,
        }
        for row in recent_rows
    ]

    # ─── 9. Defects rolled up by source execution_type ───────────────────────
    defect_stmt = (
        select(
            func.coalesce(ExecutionRun.execution_type, "manual"),
            func.count(DefectDraft.id),
        )
        .outerjoin(ExecutionResult, ExecutionResult.id == DefectDraft.execution_result_id)
        .outerjoin(ExecutionRun, ExecutionRun.id == ExecutionResult.execution_run_id)
        .where(DefectDraft.project_id == project_id)
        .group_by(ExecutionRun.execution_type)
    )
    defect_rows = (await db.execute(defect_stmt)).all()
    defects_by_type: dict[str, int] = {row[0] or "manual": int(row[1] or 0) for row in defect_rows}
    total_defects = sum(defects_by_type.values())

    # ─── 10. Quick insights ──────────────────────────────────────────────────
    # Post-migration 025, AI-assisted runs are execution_type='automation' + a
    # metadata.ai_assisted flag, so this ai_summary will be None going forward.
    # The AI-specific pass-rate insight below will simply not fire until we add
    # a metadata-aware subquery (see roadmap: Phase 4 Run Builder + insights).
    ai_summary = next((b for b in by_type if b["execution_type"] == "ai"), None)
    auto_summary = next((b for b in by_type if b["execution_type"] == "automation"), None)
    overall_executed = max(int(passed_results) + int(failed_results) + int(skipped_results) + blocked_results, 1)
    overall_pass_rate = round((int(passed_results) / overall_executed) * 100, 1)

    insights: list[dict[str, str]] = []
    if ai_summary and ai_summary["passed"] + ai_summary["failed"] > 0:
        diff = round(ai_summary["pass_rate"] - overall_pass_rate, 1)
        if diff > 0:
            insights.append({
                "kind": "ai_pass_rate",
                "title": f"AI executions have {diff}% higher pass rate",
                "body": f"AI pass rate is {ai_summary['pass_rate']}% vs overall {overall_pass_rate}%",
            })
    if blocked_results > 0:
        insights.append({
            "kind": "blocked",
            "title": f"{blocked_results} test runs are blocked",
            "body": "Environment or data issues are the top reason",
        })
    if review_required_runs > 0:
        insights.append({
            "kind": "review",
            "title": f"{review_required_runs} AI runs awaiting human review",
            "body": "Confidence threshold or policy flag triggered review",
        })
    if total_defects > 0:
        insights.append({
            "kind": "defects",
            "title": f"Defects found in this cycle",
            "body": f"{total_defects} defects logged across all execution types",
        })

    return {
        "kpis": {
            "total_executions": total_runs,
            "total_test_cases": int(total_tests or 0),
            "passed": int(passed_results or 0),
            "failed": int(failed_results or 0),
            "skipped": int(skipped_results or 0),
            "blocked": blocked_results,
            "in_progress": in_progress_runs,
            "review_required": review_required_runs,
            "avg_execution_seconds": float(avg_seconds or 0),
            "total_execution_seconds": float(total_seconds or 0),
            "overall_pass_rate": overall_pass_rate,
        },
        "by_type": by_type,
        "by_environment": by_environment,
        "by_module": by_module,
        "trend": trend,
        "recent_runs": recent_runs,
        "defects": {
            "total": total_defects,
            "by_type": defects_by_type,
        },
        "insights": insights,
        "filters_applied": {
            "project_id": project_id,
            "environment": environment,
            "execution_type": execution_type,
            "date_from": date_from.isoformat() if date_from else None,
            "date_to": date_to.isoformat() if date_to else None,
        },
    }
