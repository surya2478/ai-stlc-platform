"""Abstractions for external test data tool integrations."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import get_settings

settings = get_settings()


@dataclass
class ExternalGenerationResult:
    generation_status: str
    integration_status: str
    generated_records: list[dict[str, Any]]


class ExternalTestDataToolClient:
    async def create_generation_request(self, request_payload: dict[str, Any]) -> ExternalGenerationResult:
        raise NotImplementedError

    async def get_generation_status(self, external_reference: str) -> str:
        raise NotImplementedError

    async def fetch_generated_data(self, external_reference: str) -> list[dict[str, Any]]:
        raise NotImplementedError


class MockTestDataToolClient(ExternalTestDataToolClient):
    async def create_generation_request(self, request_payload: dict[str, Any]) -> ExternalGenerationResult:
        demo_mode = settings.app_env == "local" and settings.app_debug
        if not demo_mode:
            return ExternalGenerationResult(
                generation_status="pending_external_generation",
                integration_status="pending_manual_update",
                generated_records=[],
            )

        count = min(int(request_payload.get("number_of_records", 1) or 1), 25)
        rows = []
        for index in range(1, count + 1):
            rows.append({
                "mock_record": True,
                "demo_mode": True,
                "sequence": index,
                "data_type": request_payload.get("data_type"),
                "telecom_domain": request_payload.get("telecom_domain"),
                "environment": request_payload.get("environment"),
            })
        return ExternalGenerationResult(
            generation_status="generated",
            integration_status="demo_generated",
            generated_records=rows,
        )

    async def get_generation_status(self, external_reference: str) -> str:
        return "generated"

    async def fetch_generated_data(self, external_reference: str) -> list[dict[str, Any]]:
        return []


class UnsupportedExternalToolClient(ExternalTestDataToolClient):
    async def create_generation_request(self, request_payload: dict[str, Any]) -> ExternalGenerationResult:
        return ExternalGenerationResult(
            generation_status="pending_external_generation",
            integration_status="pending_external_generation",
            generated_records=[],
        )

    async def get_generation_status(self, external_reference: str) -> str:
        return "pending_external_generation"

    async def fetch_generated_data(self, external_reference: str) -> list[dict[str, Any]]:
        return []


def get_external_test_data_tool_client(tool_name: str) -> ExternalTestDataToolClient:
    if tool_name == "Mock":
        return MockTestDataToolClient()
    return UnsupportedExternalToolClient()
