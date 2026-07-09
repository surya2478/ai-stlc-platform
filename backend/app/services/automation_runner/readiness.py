"""
Environment Readiness Check (Phase 3.2).

Blocking gate run before Playwright MCP discovery and before script
execution — surfaces one clear, actionable reason per failed check instead
of an opaque timeout or crash deep inside a browser session.

Checks (per the plan): application URL reachable, credentials configured,
required test data present, API dependency healthy, DB validation endpoint
reachable, browser deps installed, environment not under maintenance.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

import httpx

from app.services.automation_runner import preflight


@dataclass(slots=True)
class ReadinessCheck:
    name: str
    passed: bool
    detail: str

    def as_dict(self) -> dict:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class ReadinessResult:
    checks: list[ReadinessCheck] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def blockers(self) -> list[ReadinessCheck]:
        return [c for c in self.checks if not c.passed]

    def as_dict(self) -> dict:
        return {"ready": self.ready, "checks": [c.as_dict() for c in self.checks]}


@dataclass
class ReadinessInputs:
    application_url: str | None = None
    api_health_url: str | None = None
    db_validation_endpoint: str | None = None
    storage_state_path: str | None = None
    secrets_path: str | None = None
    # Not every flow needs authentication (e.g. a public production-sanity
    # page) — credentials are only checked when the caller says this run
    # actually needs to log in.
    credentials_required: bool = False
    test_data_present: bool = True
    test_data_detail: str = "No test data requirement declared for this check — skipped."
    environment_under_maintenance: bool = False
    maintenance_detail: str = ""
    framework: str = "playwright"


async def _check_url(url: str | None, *, name: str, timeout: float = 8.0, required: bool = True) -> ReadinessCheck:
    if not url:
        if required:
            return ReadinessCheck(name, False, "No URL configured — check Project Settings → Applications & Environments.")
        return ReadinessCheck(name, True, "Not configured — skipped (optional dependency).")
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
    except httpx.HTTPError as exc:
        return ReadinessCheck(name, False, f"{url} unreachable: {exc}")
    if response.status_code >= 500:
        return ReadinessCheck(name, False, f"{url} responded {response.status_code} (server error)")
    return ReadinessCheck(name, True, f"{url} responded {response.status_code}")


def _check_credentials(inputs: ReadinessInputs) -> ReadinessCheck:
    path = inputs.storage_state_path or inputs.secrets_path
    if not path:
        if not inputs.credentials_required:
            return ReadinessCheck("credentials_configured", True, "Not required for this flow — skipped.")
        return ReadinessCheck(
            "credentials_configured", False,
            "No storage-state or secrets file configured for this environment — "
            "discovery cannot log in. Configure one in Project Settings → Applications & Environments.",
        )
    if not os.path.exists(path):
        return ReadinessCheck("credentials_configured", False, f"Configured credentials file not found: {path}")
    if os.path.getsize(path) == 0:
        return ReadinessCheck("credentials_configured", False, f"Configured credentials file is empty: {path}")
    return ReadinessCheck("credentials_configured", True, f"Credentials file present: {path}")


def _check_browser_deps(framework: str) -> ReadinessCheck:
    available, detail = preflight.is_available(framework)
    return ReadinessCheck("browser_deps_installed", available, detail)


def _check_maintenance(inputs: ReadinessInputs) -> ReadinessCheck:
    if inputs.environment_under_maintenance:
        return ReadinessCheck(
            "environment_not_under_maintenance", False,
            inputs.maintenance_detail or "Environment is flagged as under maintenance.",
        )
    return ReadinessCheck("environment_not_under_maintenance", True, "Not flagged under maintenance.")


def _check_test_data(inputs: ReadinessInputs) -> ReadinessCheck:
    return ReadinessCheck("test_data_present", inputs.test_data_present, inputs.test_data_detail)


async def check_readiness(inputs: ReadinessInputs) -> ReadinessResult:
    checks = [
        await _check_url(inputs.application_url, name="application_url_reachable", required=True),
        _check_credentials(inputs),
        _check_test_data(inputs),
        await _check_url(inputs.api_health_url, name="api_dependency_healthy", required=False),
        await _check_url(inputs.db_validation_endpoint, name="db_validation_endpoint_reachable", required=False),
        _check_browser_deps(inputs.framework),
        _check_maintenance(inputs),
    ]
    return ReadinessResult(checks=checks)
