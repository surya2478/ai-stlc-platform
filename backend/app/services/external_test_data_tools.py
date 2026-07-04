"""Abstractions for external test data tool integrations."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from app.config import get_settings
from app.services.test_data_generation.faker_engine import FakerEngineError, generate_records

logger = logging.getLogger(__name__)
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


class LocalFakerToolClient(ExternalTestDataToolClient):
    """Synthetic data generator backed by the Faker library + telco providers.

    Reads `schema_json` from the request payload (see faker_engine.generate_records
    for the shape). On schema errors the request lands as `failed` with the
    Faker engine's message so the UI can show a useful error.
    """

    async def create_generation_request(self, request_payload: dict[str, Any]) -> ExternalGenerationResult:
        schema = request_payload.get("schema_json") or {}
        count = int(request_payload.get("number_of_records", 1) or 1)
        try:
            rows = generate_records(schema, count)
        except FakerEngineError as exc:
            logger.warning("Faker schema rejected: %s", exc)
            return ExternalGenerationResult(
                generation_status="failed",
                integration_status="schema_error",
                generated_records=[{"_faker_error": str(exc)}],
            )
        except Exception:
            logger.exception("Faker generation crashed unexpectedly")
            return ExternalGenerationResult(
                generation_status="failed",
                integration_status="engine_error",
                generated_records=[],
            )
        return ExternalGenerationResult(
            generation_status="generated" if rows else "failed",
            integration_status="local_faker",
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
    if tool_name == "Faker":
        return LocalFakerToolClient()
    return UnsupportedExternalToolClient()
