from datetime import datetime, timezone

import anyio
import pytest

from app.models.automation_script import AutomationScript
from app.models.locator_map import LocatorMapEntry
from app.models.report import Report
from app.services import automation_baseline_service as baseline


class _Result:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _FakeDB:
    """Replays queued responses in call order — mirrors the pattern already
    used in test_async_agent_workflow.py's `_AgentDB`, scoped to what
    automation_baseline_service actually calls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.added = []

    async def execute(self, _stmt):
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _Result(values=value)
        return _Result(value=value)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        self.added.append(obj)

    async def flush(self):
        return None


def _script(id_: int, code: str, **overrides) -> AutomationScript:
    data = {
        "id": id_, "project_id": 1, "created_by": 1, "script_id": f"AS-{id_}",
        "framework": "playwright", "code": code, "status": "ai_draft", "version": 1,
    }
    data.update(overrides)
    return AutomationScript(**data)


def _locator(id_: int, confidence: int, failure_count: int = 0) -> LocatorMapEntry:
    return LocatorMapEntry(
        id=id_, project_id=1, page="/login", element_name=f"el{id_}",
        recommended_locator="#x", recommended_strategy="css",
        confidence_score=confidence, failure_count=failure_count,
    )


FLAKY_SCRIPT = """
import { test, expect } from '@playwright/test';
test('flaky', async ({ page }) => {
  await page.goto('/login');
  await page.waitForTimeout(5000);
});
"""

CLEAN_SCRIPT = """
import { test, expect } from '@playwright/test';
test('clean', async ({ page }) => {
  await page.goto('/login');
  await expect(page.getByRole('button', { name: 'Submit' })).toBeVisible();
});
"""


def test_capture_automation_baseline_aggregates_counts_and_static_findings():
    db = _FakeDB([
        4,                                   # generation_runs_total
        3,                                   # generation_runs_completed
        10,                                  # execution_results_total
        7,                                   # execution_passed
        [_script(1, FLAKY_SCRIPT), _script(2, CLEAN_SCRIPT)],
        2,                                   # root_script_count (version==1)
        [],                                  # locator_entries
        0,                                   # dry_run_results_total
        0,                                   # dry_run_results_passed
    ])

    snapshot = anyio.run(baseline.capture_automation_baseline, db, 1)

    assert snapshot.project_id == 1
    assert snapshot.script_count == 2
    assert snapshot.generation_runs_total == 4
    assert snapshot.generation_runs_completed == 3
    assert snapshot.generation_success_rate == 0.75
    assert snapshot.execution_results_total == 10
    assert snapshot.execution_pass_rate == 0.7
    assert snapshot.hard_wait_count >= 1
    assert snapshot.avg_health_score is not None
    # No repair-loop versions in this project -> 0.0, not None (None is
    # reserved for "can't compute", e.g. zero root scripts / no locator data).
    assert snapshot.avg_repairs_per_script == 0.0
    assert snapshot.locator_failure_rate is None
    assert snapshot.dry_run_stability is None


def test_capture_automation_baseline_handles_empty_project():
    db = _FakeDB([0, 0, 0, 0, [], 0, [], 0, 0])

    snapshot = anyio.run(baseline.capture_automation_baseline, db, 1)

    assert snapshot.script_count == 0
    assert snapshot.generation_success_rate is None
    assert snapshot.execution_pass_rate is None
    assert snapshot.avg_health_score is None
    assert snapshot.avg_repairs_per_script is None  # root_script_count == 0
    assert snapshot.locator_failure_rate is None
    assert snapshot.grounded_pass_rate is None
    assert snapshot.repair_loop_success_rate is None
    assert snapshot.dry_run_stability is None


def test_capture_automation_baseline_computes_phase4_metrics():
    grounded_script = _script(
        1, CLEAN_SCRIPT, status="dry_run_passed", version=1,
        metadata_={"grounding": {"grounded": True}},
    )
    ungrounded_script = _script(2, FLAKY_SCRIPT, status="generated", version=1)
    resolved_repair = _script(
        3, CLEAN_SCRIPT, status="dry_run_passed", version=2,
        metadata_={"source": "repair_loop"},
    )
    exhausted_repair = _script(
        4, FLAKY_SCRIPT, status="static_passed", version=2,
        metadata_={"source": "repair_loop", "repair_loop_exhausted": True},
    )

    db = _FakeDB([
        4, 3, 10, 7,
        [grounded_script, ungrounded_script, resolved_repair, exhausted_repair],
        2,                                        # root_script_count (version==1: scripts 1,2)
        [_locator(1, confidence=80, failure_count=1), _locator(2, confidence=40, failure_count=0)],
        20,                                        # dry_run_results_total
        15,                                        # dry_run_results_passed
    ])

    snapshot = anyio.run(baseline.capture_automation_baseline, db, 1)

    assert snapshot.avg_repairs_per_script == 1.0  # 2 repair versions / 2 root scripts
    assert snapshot.locator_failure_rate == 0.5    # 1 of 2 locator entries has failures
    assert snapshot.avg_locator_confidence == 0.6  # (80 + 40) / (100 * 2)
    assert snapshot.grounded_pass_rate == 1.0       # the one grounded script is dry_run_passed
    assert snapshot.repair_loop_success_rate == 0.5  # 1 resolved of 2 repair versions
    assert snapshot.dry_run_stability == 0.75


def test_capture_and_persist_baseline_creates_report_row():
    db = _FakeDB([2, 2, 0, 0, [_script(1, CLEAN_SCRIPT)], 1, [], 0, 0])

    async def run():
        return await baseline.capture_and_persist_baseline(db, project_id=1, user_id=9)

    report = anyio.run(run)

    assert report in db.added
    assert report.project_id == 1
    assert report.created_by == 9
    assert report.report_type == "automation_baseline"
    assert report.status == "generated"
    assert report.execution_metrics["script_count"] == 1
    assert report.execution_metrics["generation_success_rate"] == 1.0
    assert report.metadata_ == {"snapshot_kind": "pre_mcp_baseline"}


def test_capture_and_persist_comparison_diffs_against_earliest_baseline():
    baseline_report = Report(
        id=1, project_id=1, created_by=9, report_id="RPT-0001",
        report_type="automation_baseline", title="Automation Generation Baseline",
        execution_metrics={
            "execution_pass_rate": 0.5, "grounded_pass_rate": None,
            "avg_locator_confidence": None, "dry_run_stability": None,
        },
        status="generated", metadata_={"snapshot_kind": "pre_mcp_baseline"},
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    db = _FakeDB([
        [baseline_report],                   # _earliest_pre_mcp_baseline
        4, 3, 10, 9,                          # fresh snapshot counts
        [_script(1, CLEAN_SCRIPT, status="dry_run_passed", metadata_={"grounding": {"grounded": True}})],
        1, [_locator(1, confidence=90)],      # root_script_count, locator_entries
        5, 5,                                  # dry_run_results_total, passed
    ])

    async def run():
        return await baseline.capture_and_persist_comparison(db, project_id=1, user_id=9)

    report = anyio.run(run)

    assert report.report_type == "automation_baseline_comparison"
    assert report.metadata_["baseline_report_id"] == 1
    diff = report.execution_metrics["diff"]
    assert diff["execution_pass_rate"]["before"] == 0.5
    assert diff["execution_pass_rate"]["after"] == 0.9
    assert diff["execution_pass_rate"]["delta"] == pytest.approx(0.4)


def test_capture_and_persist_comparison_raises_without_prior_baseline():
    db = _FakeDB([[]])  # no baseline report found

    async def run():
        return await baseline.capture_and_persist_comparison(db, project_id=1, user_id=9)

    try:
        anyio.run(run)
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "No pre-MCP baseline found" in str(exc)
