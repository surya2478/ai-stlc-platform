"""Workspace landing-page metrics.

Every number here is read from a real table. Where the contract asks for a
metric this platform has no source for, the field is returned as `None` and
named in the response's `unavailable` map with the reason — never as `0`,
which would read as a real measurement of zero.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_script import AutomationScript
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.discovery_session import DiscoverySession
from app.models.execution import ExecutionRun
from app.models.mcp_connection import MCPConnection
from app.models.test_case import TestCase

# These three buckets must partition every status in SUITE_STATUSES, so the
# KPI card's breakdown always adds up to its total. A status that fell through
# would silently vanish from the dashboard — which is how a published suite
# went uncounted before.
_DRAFT_STATUSES = ("DRAFT", "SCOPE_SELECTED")
_ACTIVE_STATUSES = (
    "INHERITANCE_REVIEW_REQUIRED",
    "MAPPING_INCOMPLETE",
    "CONFLICT_REVIEW_REQUIRED",
    "READY_FOR_VALIDATION",
    "VALIDATION_PENDING",
    "VALIDATION_FAILED",
    "READY_FOR_REVIEW",
    "APPROVED",
    "PUBLISHED",
)
_RETIRED_STATUSES = ("ARCHIVED", "DEPRECATED")
# Sub-counts worth surfacing on their own, all real.
_IN_REVIEW_STATUSES = ("READY_FOR_REVIEW",)
_PUBLISHED_STATUSES = ("PUBLISHED",)
# ExecutionRun.status vocabulary (migration 024). There is deliberately no
# mapping from 'review_required' onto the contract's "Blocked"/"Inconclusive":
# they are different concepts and conflating them would misreport runs.
_RUNNING_STATUSES = ("running",)
_QUEUED_STATUSES = ("pending", "queued")
_AUTOMATED_SCRIPT_STATUSES = (
    "approved",
    "reviewer_approved",
    "lead_approved",
    "ci_ready",
    "executed",
)


async def _count(db: AsyncSession, model, *filters) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*filters))).scalar() or 0


async def compute_workspace_kpis(db: AsyncSession, *, project_id: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # ── 1. Automation Suites ──
    suites_total = await _count(db, AutomationSuite, AutomationSuite.project_id == project_id)
    suites_draft = await _count(
        db, AutomationSuite, AutomationSuite.project_id == project_id, AutomationSuite.status.in_(_DRAFT_STATUSES)
    )
    suites_active = await _count(
        db, AutomationSuite, AutomationSuite.project_id == project_id, AutomationSuite.status.in_(_ACTIVE_STATUSES)
    )
    suites_archived = await _count(
        db,
        AutomationSuite,
        AutomationSuite.project_id == project_id,
        AutomationSuite.status.in_(_RETIRED_STATUSES),
    )
    suites_in_review = await _count(
        db,
        AutomationSuite,
        AutomationSuite.project_id == project_id,
        AutomationSuite.status.in_(_IN_REVIEW_STATUSES),
    )
    suites_published = await _count(
        db,
        AutomationSuite,
        AutomationSuite.project_id == project_id,
        AutomationSuite.status.in_(_PUBLISHED_STATUSES),
    )
    created_last_7d = await _count(
        db, AutomationSuite, AutomationSuite.project_id == project_id, AutomationSuite.created_at >= week_ago
    )
    created_prev_7d = await _count(
        db,
        AutomationSuite,
        AutomationSuite.project_id == project_id,
        AutomationSuite.created_at >= two_weeks_ago,
        AutomationSuite.created_at < week_ago,
    )

    # ── 2. Test Cases linked through suite membership ──
    linked_ids_query = (
        select(AutomationSuiteTestCase.test_case_id)
        .join(AutomationSuite, AutomationSuite.id == AutomationSuiteTestCase.suite_id)
        .where(
            AutomationSuite.project_id == project_id,
            AutomationSuite.status != "ARCHIVED",
            AutomationSuiteTestCase.inclusion_status == "included",
        )
        .distinct()
    )
    linked_ids = list((await db.execute(linked_ids_query)).scalars().all())
    linked_total = len(linked_ids)

    automation_candidates = 0
    automated = 0
    if linked_ids:
        automation_candidates = await _count(
            db, TestCase, TestCase.id.in_(linked_ids), TestCase.automation_candidate.is_(True)
        )
        automated_by_status = set(
            (
                await db.execute(
                    select(TestCase.id).where(TestCase.id.in_(linked_ids), TestCase.automation_status == "automated")
                )
            )
            .scalars()
            .all()
        )
        automated_by_script = set(
            (
                await db.execute(
                    select(AutomationScript.test_case_id).where(
                        AutomationScript.test_case_id.in_(linked_ids),
                        AutomationScript.status.in_(_AUTOMATED_SCRIPT_STATUSES),
                    )
                )
            )
            .scalars()
            .all()
        )
        automated = len(automated_by_status | automated_by_script)

    # ── 3. Automation Assets ──
    scripts = 0
    recordings = 0
    if linked_ids:
        scripts = await _count(db, AutomationScript, AutomationScript.test_case_id.in_(linked_ids))
        recordings = await _count(db, DiscoverySession, DiscoverySession.test_case_id.in_(linked_ids))

    # ── 4. Active Executions ──
    running = await _count(
        db, ExecutionRun, ExecutionRun.project_id == project_id, ExecutionRun.status.in_(_RUNNING_STATUSES)
    )
    queued = await _count(
        db, ExecutionRun, ExecutionRun.project_id == project_id, ExecutionRun.status.in_(_QUEUED_STATUSES)
    )
    review_required = await _count(
        db, ExecutionRun, ExecutionRun.project_id == project_id, ExecutionRun.status == "review_required"
    )

    # ── 5. Success Rate (project-wide: executions carry no suite link) ──
    pass_rate_7d = await _pass_rate(db, project_id=project_id, since=week_ago, until=now)
    pass_rate_prev_7d = await _pass_rate(db, project_id=project_id, since=two_weeks_ago, until=week_ago)
    trend = await _daily_pass_rate_trend(db, project_id=project_id, days=7, now=now)

    return {
        "suites": {
            "total": suites_total,
            "draft": suites_draft,
            "active": suites_active,
            "archived": suites_archived,
            "in_review": suites_in_review,
            "published": suites_published,
            "created_last_7d": created_last_7d,
            "created_prev_7d": created_prev_7d,
            "validation_pending": None,
        },
        "test_cases": {
            "linked_total": linked_total,
            "automation_candidates": automation_candidates,
            "automated": automated,
            "coverage_pct": round(100 * automated / linked_total) if linked_total else 0,
        },
        "automation_assets": {
            "scripts": scripts,
            "recordings": recordings,
            "automation_ir": None,
            "page_objects": None,
            "reusable_components": None,
            "api_collections": None,
            "object_repositories": None,
            "git_repositories": None,
        },
        "active_executions": {
            "running": running,
            "queued": queued,
            "review_required": review_required,
            "blocked": None,
            "inconclusive": None,
        },
        "success_rate": {
            "pass_rate_7d": pass_rate_7d,
            "pass_rate_prev_7d": pass_rate_prev_7d,
            "trend": trend,
            "scope": "project",
        },
        "unavailable": {
            "suites.validation_pending": "No validation subsystem exists yet (UI-023 Validation and Review).",
            "automation_assets.automation_ir": "No Automation IR entity exists yet (UI-020).",
            "automation_assets.page_objects": "No page-object entity exists yet.",
            "automation_assets.reusable_components": "No reusable-component entity exists yet (P2-S3).",
            "automation_assets.api_collections": "No API-collection entity exists yet.",
            "automation_assets.object_repositories": "No object-repository entity exists yet.",
            "automation_assets.git_repositories": "No git-repository entity exists yet.",
            "active_executions.blocked": "'blocked' is not an execution status in this platform.",
            "active_executions.inconclusive": "'inconclusive' is not an execution status in this platform.",
            "success_rate.scope": "Executions carry no link to a suite, so this is project-wide, not suite-scoped.",
        },
    }


async def _pass_rate(db: AsyncSession, *, project_id: int, since: datetime, until: datetime) -> float | None:
    row = (
        await db.execute(
            select(func.coalesce(func.sum(ExecutionRun.passed), 0), func.coalesce(func.sum(ExecutionRun.failed), 0))
            .where(
                ExecutionRun.project_id == project_id,
                ExecutionRun.status == "completed",
                ExecutionRun.started_at >= since,
                ExecutionRun.started_at < until,
            )
        )
    ).one()
    passed, failed = int(row[0] or 0), int(row[1] or 0)
    decided = passed + failed
    # No completed runs in the window is not a 0% pass rate.
    return round(100 * passed / decided, 1) if decided else None


async def _daily_pass_rate_trend(
    db: AsyncSession, *, project_id: int, days: int, now: datetime
) -> list[dict[str, Any]]:
    buckets: list[dict[str, Any]] = []
    for offset in range(days - 1, -1, -1):
        day_start = (now - timedelta(days=offset)).replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        buckets.append(
            {
                "date": day_start.date().isoformat(),
                "pass_rate": await _pass_rate(db, project_id=project_id, since=day_start, until=day_end),
            }
        )
    return buckets


async def list_active_executions(db: AsyncSession, *, project_id: int, limit: int = 20) -> dict[str, Any]:
    """The Active Executions feed.

    `automation_test_suite` is `ExecutionRun.suite_name` verbatim — a free
    string with no foreign key to an automation suite. It is emitted with
    `suite_link_available: false` rather than name-matched onto a suite, which
    would be a fabricated relationship.
    """
    result = await db.execute(
        select(ExecutionRun)
        .where(
            ExecutionRun.project_id == project_id,
            ExecutionRun.status.in_(_RUNNING_STATUSES + _QUEUED_STATUSES + ("review_required",)),
        )
        .order_by(ExecutionRun.started_at.desc().nulls_last(), ExecutionRun.id.desc())
        .limit(limit)
    )
    runs = list(result.scalars().all())

    items = []
    for run in runs:
        decided = (run.passed or 0) + (run.failed or 0) + (run.skipped or 0)
        items.append(
            {
                "id": run.id,
                "execution_id": run.execution_id,
                "automation_test_suite": run.suite_name,
                "suite_link_available": False,
                "environment": run.environment,
                "execution_type": run.execution_type,
                "status": run.status,
                "started_at": run.started_at,
                "total_tests": run.total_tests,
                "progress_pct": round(100 * decided / run.total_tests) if run.total_tests else None,
                "framework": None,
                "execution_group": None,
            }
        )
    return {
        "items": items,
        "unavailable": {
            "framework": "ExecutionRun does not record a framework.",
            "execution_group": "Execution groups arrive with Phase B.",
            "suite_link_available": "Executions carry no foreign key to an automation suite.",
        },
    }


async def compute_footer_status(db: AsyncSession, *, project_id: int) -> dict[str, Any]:
    """Footer strip. Agent availability is real; the other two have no source."""
    rows = await db.execute(
        select(MCPConnection.status, func.count()).where(MCPConnection.project_id == project_id).group_by(
            MCPConnection.status
        )
    )
    by_status = {status: count for status, count in rows.all()}
    total = sum(by_status.values())

    return {
        "agents": {
            "total": total,
            "connected": by_status.get("connected", 0),
            "error": by_status.get("error", 0),
            "not_configured": by_status.get("not_configured", 0),
        },
        "qa_environment": None,
        "storage_usage": None,
        "server_time": datetime.now(timezone.utc),
        "unavailable": {
            "qa_environment": "No environment-health subsystem exists yet (P1-S7 / P2-S1).",
            "storage_usage": "No storage-usage subsystem exists yet.",
        },
    }
