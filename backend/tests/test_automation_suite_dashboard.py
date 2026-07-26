"""Dashboard metrics — the honest-absence contract.

The point of these tests is that a metric with no source is `None` and named
in `unavailable`, never `0`. A zero would read as a real measurement.
"""
import anyio

from app.models.automation_suite import SUITE_STATUSES
from app.services.automation_suite import dashboard as svc


def test_the_suite_buckets_partition_every_status():
    """Draft/active/retired must cover all statuses exactly once.

    A status falling through a bucket makes the KPI breakdown stop adding up to
    its own total — which is how a PUBLISHED suite once went uncounted.
    """
    buckets = (svc._DRAFT_STATUSES, svc._ACTIVE_STATUSES, svc._RETIRED_STATUSES)
    covered = [s for bucket in buckets for s in bucket]

    assert set(covered) == set(SUITE_STATUSES), (
        "every suite status must sit in exactly one dashboard bucket"
    )
    assert len(covered) == len(set(covered)), "a status is counted in two buckets"


def test_sub_counts_are_subsets_of_the_active_bucket():
    assert set(svc._IN_REVIEW_STATUSES) <= set(svc._ACTIVE_STATUSES)
    assert set(svc._PUBLISHED_STATUSES) <= set(svc._ACTIVE_STATUSES)


class _ExecuteResult:
    def __init__(self, values, scalar=0):
        self._values = list(values)
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._values)

    def scalar(self):
        return self._scalar

    def one(self):
        return self._values[0] if self._values else (0, 0)


class _EmptyDB:
    """A project with no suites, no assets and no executions."""

    async def execute(self, stmt):
        statement = str(stmt)
        if "sum(" in statement:
            return _ExecuteResult([(0, 0)])
        if "count(" in statement:
            return _ExecuteResult([], scalar=0)
        return _ExecuteResult([])


def test_metrics_without_a_source_are_none_and_explained():
    kpis = anyio.run(lambda: svc.compute_workspace_kpis(_EmptyDB(), project_id=1))

    assert kpis["suites"]["validation_pending"] is None
    for field in (
        "automation_ir",
        "page_objects",
        "reusable_components",
        "api_collections",
        "object_repositories",
        "git_repositories",
    ):
        assert kpis["automation_assets"][field] is None, field
    assert kpis["active_executions"]["blocked"] is None
    assert kpis["active_executions"]["inconclusive"] is None

    unavailable = kpis["unavailable"]
    assert "suites.validation_pending" in unavailable
    assert "automation_assets.automation_ir" in unavailable
    assert "active_executions.blocked" in unavailable
    assert "active_executions.inconclusive" in unavailable
    # Each reason must actually say something.
    assert all(len(reason) > 10 for reason in unavailable.values())


def test_metrics_with_a_real_source_are_numbers_even_when_zero():
    kpis = anyio.run(lambda: svc.compute_workspace_kpis(_EmptyDB(), project_id=1))
    assert kpis["suites"]["total"] == 0
    assert kpis["suites"]["draft"] == 0
    assert kpis["test_cases"]["linked_total"] == 0
    assert kpis["automation_assets"]["scripts"] == 0
    assert kpis["active_executions"]["running"] == 0
    assert kpis["active_executions"]["review_required"] == 0


def test_no_completed_runs_is_an_unknown_pass_rate_not_zero_percent():
    kpis = anyio.run(lambda: svc.compute_workspace_kpis(_EmptyDB(), project_id=1))
    assert kpis["success_rate"]["pass_rate_7d"] is None
    assert kpis["success_rate"]["pass_rate_prev_7d"] is None
    assert len(kpis["success_rate"]["trend"]) == 7
    assert all(bucket["pass_rate"] is None for bucket in kpis["success_rate"]["trend"])


def test_success_rate_is_labelled_project_wide():
    """Executions carry no suite link, so the scope must be stated."""
    kpis = anyio.run(lambda: svc.compute_workspace_kpis(_EmptyDB(), project_id=1))
    assert kpis["success_rate"]["scope"] == "project"
    assert "suite" in kpis["unavailable"]["success_rate.scope"]


def test_coverage_is_zero_rather_than_dividing_by_zero():
    kpis = anyio.run(lambda: svc.compute_workspace_kpis(_EmptyDB(), project_id=1))
    assert kpis["test_cases"]["coverage_pct"] == 0


def test_footer_reports_agents_but_not_invented_health_or_storage():
    footer = anyio.run(lambda: svc.compute_footer_status(_EmptyDB(), project_id=1))
    assert footer["agents"] == {"total": 0, "connected": 0, "error": 0, "not_configured": 0}
    assert footer["qa_environment"] is None
    assert footer["storage_usage"] is None
    assert "qa_environment" in footer["unavailable"]
    assert "storage_usage" in footer["unavailable"]
    assert footer["server_time"] is not None


def test_active_executions_never_fabricates_a_suite_link():
    class _RunsDB(_EmptyDB):
        async def execute(self, stmt):
            statement = str(stmt)
            if "execution_runs" in statement and "count(" not in statement:
                return _ExecuteResult(
                    [
                        type(
                            "Run",
                            (),
                            {
                                "id": 1,
                                "execution_id": "EXE-2054",
                                "suite_name": "Postpaid Order Provisioning E2E",
                                "environment": "QA",
                                "execution_type": "automation",
                                "status": "running",
                                "started_at": None,
                                "total_tests": 4,
                                "passed": 1,
                                "failed": 0,
                                "skipped": 0,
                            },
                        )()
                    ]
                )
            return await super().execute(stmt)

    feed = anyio.run(lambda: svc.list_active_executions(_RunsDB(), project_id=1))
    row = feed["items"][0]
    # The free-text suite name is passed through, never matched onto a suite.
    assert row["automation_test_suite"] == "Postpaid Order Provisioning E2E"
    assert row["suite_link_available"] is False
    assert row["framework"] is None
    assert row["execution_group"] is None
    assert row["progress_pct"] == 25


def test_progress_is_unknown_when_a_run_has_no_test_count():
    class _ZeroTotalDB(_EmptyDB):
        async def execute(self, stmt):
            statement = str(stmt)
            if "execution_runs" in statement and "count(" not in statement:
                return _ExecuteResult(
                    [
                        type(
                            "Run",
                            (),
                            {
                                "id": 2,
                                "execution_id": "EXE-1932",
                                "suite_name": None,
                                "environment": "QA",
                                "execution_type": "automation",
                                "status": "queued",
                                "started_at": None,
                                "total_tests": 0,
                                "passed": 0,
                                "failed": 0,
                                "skipped": 0,
                            },
                        )()
                    ]
                )
            return await super().execute(stmt)

    feed = anyio.run(lambda: svc.list_active_executions(_ZeroTotalDB(), project_id=1))
    assert feed["items"][0]["progress_pct"] is None
