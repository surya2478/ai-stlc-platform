from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from app.integrations.automation.base_connector import AutomationConnector
from app.integrations.automation.result_normalizer import normalize_status
from app.integrations.automation.schemas import AutomationExecutionResult, AutomationExecutionSummary


class MockAutomationConnector(AutomationConnector):
    """Local deterministic connector used before real automation tools are integrated."""

    def _raw_status(self, external_test_case_id: str) -> str:
        digest = hashlib.sha256(external_test_case_id.encode("utf-8")).hexdigest()
        bucket = int(digest[:2], 16) % 10
        if bucket < 7:
            return "SUCCESS"
        if bucket < 9:
            return "FAILED"
        return "SKIPPED"

    def _result(self, mapping, external_run_id: str) -> AutomationExecutionResult:
        raw_status = self._raw_status(mapping.external_test_case_id)
        status = normalize_status(raw_status)
        now = datetime.now(timezone.utc).isoformat()
        slug = f"{mapping.external_tool_name.lower()}-{mapping.external_test_case_id}".replace(" ", "-")
        return AutomationExecutionResult(
            external_run_id=external_run_id,
            external_test_case_id=mapping.external_test_case_id,
            status=status,
            duration_seconds=round(12.5 + (len(mapping.external_test_case_id) % 9) * 3.25, 2),
            logs=[
                f"[{now}] Mock automation run started for {mapping.external_test_case_id}",
                f"[{now}] Raw external status: {raw_status}",
                f"[{now}] Normalized status: {status}",
            ],
            screenshot_url=f"https://mock-automation.local/artifacts/{slug}/screenshot.png",
            video_url=f"https://mock-automation.local/artifacts/{slug}/video.webm",
            log_url=f"https://mock-automation.local/artifacts/{slug}/execution.log",
            external_result_url=f"https://mock-automation.local/runs/{external_run_id}/tests/{mapping.external_test_case_id}",
            error_message="Mock failure evidence captured" if status == "failed" else None,
            raw={
                "tool": mapping.external_tool_name,
                "externalProjectId": mapping.external_project_id,
                "externalSuiteId": mapping.external_suite_id,
                "externalTestCaseId": mapping.external_test_case_id,
                "status": raw_status,
                "generatedAt": now,
            },
        )

    async def trigger_execution(self, mapping, environment: str) -> AutomationExecutionSummary:
        external_run_id = f"mock-{environment}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{mapping.id}"
        result = self._result(mapping, external_run_id)
        return AutomationExecutionSummary(
            external_run_id=external_run_id,
            status="completed",
            results=[result],
        )

    async def get_execution_status(self, external_run_id: str) -> str:
        return "completed"

    async def get_execution_results(self, external_run_id: str) -> list[AutomationExecutionResult]:
        return []

    async def sync_latest_result(self, mapping) -> AutomationExecutionResult:
        external_run_id = f"mock-sync-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{mapping.id}"
        return self._result(mapping, external_run_id)
