import pytest

from app.integrations.automation.mock_connector import MockAutomationConnector
from app.integrations.automation.result_normalizer import normalize_status


class _Mapping:
    id = 10
    external_tool_name = "Mock"
    external_project_id = "PROJECT"
    external_suite_id = "REGRESSION"
    external_test_case_id = "TC-100"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("SUCCESS", "passed"),
        ("PASS", "passed"),
        ("FAILED", "failed"),
        ("FAILURE", "failed"),
        ("BROKEN", "error"),
        ("ABORTED", "error"),
        ("SKIPPED", "skipped"),
        ("NOT_EXECUTED", "not_run"),
        ("RUNNING", "in_progress"),
        (None, "pending"),
    ],
)
def test_normalize_external_automation_status(raw, expected):
    assert normalize_status(raw) == expected


def test_mock_connector_returns_auditable_evidence():
    async def run():
        summary = await MockAutomationConnector().trigger_execution(_Mapping(), "staging")
        assert summary.status == "completed"
        assert summary.external_run_id.startswith("mock-staging-")
        assert len(summary.results) == 1
        result = summary.results[0]
        assert result.status in {"passed", "failed", "skipped"}
        assert result.external_result_url
        assert result.log_url
        assert result.raw["externalTestCaseId"] == "TC-100"

    import anyio

    anyio.run(run)
