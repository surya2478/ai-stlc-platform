from __future__ import annotations

from abc import ABC, abstractmethod

from app.integrations.automation.schemas import AutomationExecutionResult, AutomationExecutionSummary


class AutomationConnector(ABC):
    """Common contract for external automation tool integrations."""

    @abstractmethod
    async def trigger_execution(self, mapping, environment: str) -> AutomationExecutionSummary:
        raise NotImplementedError

    @abstractmethod
    async def get_execution_status(self, external_run_id: str) -> str:
        raise NotImplementedError

    @abstractmethod
    async def get_execution_results(self, external_run_id: str) -> list[AutomationExecutionResult]:
        raise NotImplementedError

    @abstractmethod
    async def sync_latest_result(self, mapping) -> AutomationExecutionResult:
        raise NotImplementedError
