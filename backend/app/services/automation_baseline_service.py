"""
Automation generation baseline metrics (Phase 0 foundation hardening).

Captures a point-in-time snapshot of automation-generation quality BEFORE
Playwright MCP grounding (Phase 3) changes how scripts are produced, so the
improvement claimed for MCP-grounded generation can be measured against a
real "before" number instead of asserted. Re-run the same capture after
Phase 4 lands and diff the two snapshots.

What's measured here is only what's honestly computable from data that
exists today:
  - script generation success rate — AgentRun(agent_name="automation_script")
    completed vs total
  - automation execution stability — ExecutionRun/ExecutionResult rows with
    execution_type="automation"
  - static quality issues per script — automation_intelligence's existing
    deterministic rule engine (hard waits, weak locators, missing
    assertions), averaged across every AutomationScript in the project

Phase 4 fills in the two fields that were placeholders here (now that
script versioning and the locator_map table exist), and adds four
grounded-generation-specific metrics so a post-MCP capture can be diffed
against the pre-MCP one (see `capture_and_persist_comparison`):
  - grounded_pass_rate — dry-run pass rate for scripts the generator
    actually grounded in a live locator catalog (metadata_.grounding.grounded)
  - avg_locator_confidence — mean confidence_score across the project's
    locator_map entries (Phase 3 discovery)
  - repair_loop_success_rate — of scripts that ever entered the bounded
    repair loop, the fraction that resolved before exhausting attempts
  - dry_run_stability — pass rate across all dry-run/repair-dry-run
    ExecutionResult rows (source_type in ("dry_run", "repair_dry_run"))
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.locator_map import LocatorMapEntry
from app.models.report import Report
from app.services.automation_intelligence import analyze_script
from app.services.display_id_service import display_id, temporary_id


@dataclass
class AutomationBaselineSnapshot:
    project_id: int
    script_count: int
    generation_runs_total: int
    generation_runs_completed: int
    generation_success_rate: float | None
    execution_results_total: int
    execution_pass_rate: float | None
    hard_wait_count: int
    weak_locator_count: int
    missing_assertion_count: int
    avg_health_score: float | None
    avg_repairs_per_script: float | None = None
    locator_failure_rate: float | None = None
    grounded_pass_rate: float | None = None
    avg_locator_confidence: float | None = None
    repair_loop_success_rate: float | None = None
    dry_run_stability: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "script_count": self.script_count,
            "generation_runs_total": self.generation_runs_total,
            "generation_runs_completed": self.generation_runs_completed,
            "generation_success_rate": self.generation_success_rate,
            "execution_results_total": self.execution_results_total,
            "execution_pass_rate": self.execution_pass_rate,
            "hard_wait_count": self.hard_wait_count,
            "weak_locator_count": self.weak_locator_count,
            "missing_assertion_count": self.missing_assertion_count,
            "avg_health_score": self.avg_health_score,
            "avg_repairs_per_script": self.avg_repairs_per_script,
            "locator_failure_rate": self.locator_failure_rate,
            "grounded_pass_rate": self.grounded_pass_rate,
            "avg_locator_confidence": self.avg_locator_confidence,
            "repair_loop_success_rate": self.repair_loop_success_rate,
            "dry_run_stability": self.dry_run_stability,
        }


def _pct(value: float | None) -> str:
    return f"{value * 100:.0f}%" if value is not None else "n/a"


async def _scalar_count(db: AsyncSession, stmt) -> int:
    return (await db.execute(stmt)).scalar() or 0


async def capture_automation_baseline(db: AsyncSession, project_id: int) -> AutomationBaselineSnapshot:
    """Compute a fresh baseline snapshot for a project. Pure read — callers
    decide whether/how to persist it (see `capture_and_persist_baseline`)."""

    gen_total = await _scalar_count(
        db,
        select(func.count(AgentRun.id)).where(
            AgentRun.project_id == project_id,
            AgentRun.agent_name == "automation_script",
        ),
    )
    gen_completed = await _scalar_count(
        db,
        select(func.count(AgentRun.id)).where(
            AgentRun.project_id == project_id,
            AgentRun.agent_name == "automation_script",
            AgentRun.status == "completed",
        ),
    )
    generation_success_rate = (gen_completed / gen_total) if gen_total else None

    exec_result_total = await _scalar_count(
        db,
        select(func.count(ExecutionResult.id))
        .join(ExecutionRun, ExecutionResult.execution_run_id == ExecutionRun.id)
        .where(
            ExecutionRun.project_id == project_id,
            ExecutionRun.execution_type == "automation",
        ),
    )
    exec_passed = await _scalar_count(
        db,
        select(func.count(ExecutionResult.id))
        .join(ExecutionRun, ExecutionResult.execution_run_id == ExecutionRun.id)
        .where(
            ExecutionRun.project_id == project_id,
            ExecutionRun.execution_type == "automation",
            ExecutionResult.status == "passed",
        ),
    )
    execution_pass_rate = (exec_passed / exec_result_total) if exec_result_total else None

    scripts = list(
        (
            await db.execute(select(AutomationScript).where(AutomationScript.project_id == project_id))
        ).scalars().all()
    )
    hard_wait_count = 0
    weak_locator_count = 0
    missing_assertion_count = 0
    health_scores: list[int] = []
    for script in scripts:
        report = analyze_script(script)
        hard_wait_count += sum(1 for r in report.recommendations if r.kind == "hard_wait")
        weak_locator_count += len(report.locators)
        missing_assertion_count += len(report.assertions)
        health_scores.append(report.health.overall)
    avg_health_score = (sum(health_scores) / len(health_scores)) if health_scores else None

    # avg_repairs_per_script: total repair-attempt versions produced, divided
    # by the count of originally-generated (version==1) scripts — an
    # approximation, since repair versions don't carry a "family" grouping
    # key back to a single root script, only an immediate parent_script_id.
    root_script_count = await _scalar_count(
        db,
        select(func.count(AutomationScript.id)).where(
            AutomationScript.project_id == project_id, AutomationScript.version == 1,
        ),
    )
    repair_versions = [s for s in scripts if (s.metadata_ or {}).get("source") == "repair_loop"]
    avg_repairs_per_script = (len(repair_versions) / root_script_count) if root_script_count else None

    locator_entries = list(
        (
            await db.execute(select(LocatorMapEntry).where(LocatorMapEntry.project_id == project_id))
        ).scalars().all()
    )
    locator_failure_rate = (
        sum(1 for e in locator_entries if e.failure_count > 0) / len(locator_entries)
        if locator_entries else None
    )
    avg_locator_confidence = (
        sum(e.confidence_score for e in locator_entries) / (100.0 * len(locator_entries))
        if locator_entries else None
    )

    grounded_scripts = [s for s in scripts if (s.metadata_ or {}).get("grounding", {}).get("grounded")]
    grounded_dry_run_passed = sum(
        1 for s in grounded_scripts
        if s.status in ("dry_run_passed", "reviewer_approved", "lead_approved", "ci_ready")
    )
    grounded_pass_rate = (grounded_dry_run_passed / len(grounded_scripts)) if grounded_scripts else None

    resolved_repairs = sum(1 for s in repair_versions if not (s.metadata_ or {}).get("repair_loop_exhausted"))
    repair_loop_success_rate = (resolved_repairs / len(repair_versions)) if repair_versions else None

    dry_run_results_total = await _scalar_count(
        db,
        select(func.count(ExecutionResult.id))
        .join(ExecutionRun, ExecutionResult.execution_run_id == ExecutionRun.id)
        .where(
            ExecutionRun.project_id == project_id,
            ExecutionRun.source_type.in_(("dry_run", "repair_dry_run")),
        ),
    )
    dry_run_results_passed = await _scalar_count(
        db,
        select(func.count(ExecutionResult.id))
        .join(ExecutionRun, ExecutionResult.execution_run_id == ExecutionRun.id)
        .where(
            ExecutionRun.project_id == project_id,
            ExecutionRun.source_type.in_(("dry_run", "repair_dry_run")),
            ExecutionResult.status == "pass",
        ),
    )
    dry_run_stability = (dry_run_results_passed / dry_run_results_total) if dry_run_results_total else None

    return AutomationBaselineSnapshot(
        project_id=project_id,
        script_count=len(scripts),
        generation_runs_total=gen_total,
        generation_runs_completed=gen_completed,
        generation_success_rate=generation_success_rate,
        execution_results_total=exec_result_total,
        execution_pass_rate=execution_pass_rate,
        hard_wait_count=hard_wait_count,
        weak_locator_count=weak_locator_count,
        missing_assertion_count=missing_assertion_count,
        avg_health_score=avg_health_score,
        avg_repairs_per_script=avg_repairs_per_script,
        locator_failure_rate=locator_failure_rate,
        grounded_pass_rate=grounded_pass_rate,
        avg_locator_confidence=avg_locator_confidence,
        repair_loop_success_rate=repair_loop_success_rate,
        dry_run_stability=dry_run_stability,
    )


async def capture_and_persist_baseline(db: AsyncSession, *, project_id: int, user_id: int) -> Report:
    """Capture the snapshot and store it as a Report (report_type=
    'automation_baseline') so it survives across sessions and can be diffed
    against a later post-MCP capture. Reuses the existing Report model
    rather than adding a new table for a single JSONB snapshot."""
    snapshot = await capture_automation_baseline(db, project_id)
    report = Report(
        project_id=project_id,
        created_by=user_id,
        report_id=temporary_id("RPT"),
        report_type="automation_baseline",
        title="Automation Generation Baseline",
        summary=(
            f"{snapshot.script_count} automation script(s) — "
            f"{_pct(snapshot.generation_success_rate)} generation success rate, "
            f"{_pct(snapshot.execution_pass_rate)} execution pass rate, "
            f"{snapshot.hard_wait_count} hard wait(s), "
            f"{snapshot.weak_locator_count} weak locator finding(s), "
            f"{snapshot.missing_assertion_count} missing assertion finding(s)."
        ),
        execution_metrics=snapshot.as_dict(),
        status="generated",
        metadata_={"snapshot_kind": "pre_mcp_baseline"},
    )
    db.add(report)
    await db.flush()
    report.report_id = display_id("RPT", report.id)
    await db.flush()
    return report


_COMPARISON_METRICS = (
    "generation_success_rate", "execution_pass_rate", "avg_health_score",
    "avg_repairs_per_script", "locator_failure_rate", "grounded_pass_rate",
    "avg_locator_confidence", "repair_loop_success_rate", "dry_run_stability",
)


async def _earliest_pre_mcp_baseline(db: AsyncSession, project_id: int) -> Report | None:
    result = await db.execute(
        select(Report)
        .where(
            Report.project_id == project_id,
            Report.report_type == "automation_baseline",
            Report.metadata_["snapshot_kind"].as_string() == "pre_mcp_baseline",
        )
        .order_by(Report.created_at.asc())
    )
    return result.scalars().first()


def _diff_snapshots(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    diff: dict[str, Any] = {}
    for key in _COMPARISON_METRICS:
        b, a = before.get(key), after.get(key)
        delta = (a - b) if isinstance(b, (int, float)) and isinstance(a, (int, float)) else None
        diff[key] = {"before": b, "after": a, "delta": delta}
    return diff


async def capture_and_persist_comparison(db: AsyncSession, *, project_id: int, user_id: int) -> Report:
    """Capture a fresh ("post_mcp") snapshot and diff it against the earliest
    pre-MCP baseline captured for this project (see
    `capture_and_persist_baseline`) — this is the "metrics dashboard shows
    baseline vs grounded comparison" exit criterion from Phase 4 of the plan.
    Raises ValueError if no pre-MCP baseline exists yet to compare against.
    """
    baseline_report = await _earliest_pre_mcp_baseline(db, project_id)
    if baseline_report is None:
        raise ValueError(
            "No pre-MCP baseline found for this project — capture one via "
            "POST /reports/automation-baseline/{project_id} first."
        )

    after_snapshot = await capture_automation_baseline(db, project_id)
    before = baseline_report.execution_metrics or {}
    after = after_snapshot.as_dict()
    diff = _diff_snapshots(before, after)

    report = Report(
        project_id=project_id,
        created_by=user_id,
        report_id=temporary_id("RPT"),
        report_type="automation_baseline_comparison",
        title="Automation Baseline vs Grounded Generation Comparison",
        summary=(
            f"Compared against baseline captured {baseline_report.created_at:%Y-%m-%d}: "
            f"execution pass rate {_pct(before.get('execution_pass_rate'))} -> "
            f"{_pct(after.get('execution_pass_rate'))}, "
            f"grounded pass rate now {_pct(after.get('grounded_pass_rate'))}, "
            f"avg locator confidence {_pct(after.get('avg_locator_confidence'))}."
        ),
        execution_metrics={"before": before, "after": after, "diff": diff},
        status="generated",
        metadata_={"snapshot_kind": "post_mcp_comparison", "baseline_report_id": baseline_report.id},
    )
    db.add(report)
    await db.flush()
    report.report_id = display_id("RPT", report.id)
    await db.flush()
    return report
