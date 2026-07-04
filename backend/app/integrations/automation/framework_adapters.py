from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


def _read_value(entity: Any, field: str, default: Any = None) -> Any:
    if isinstance(entity, dict):
        return entity.get(field, default)
    return getattr(entity, field, default)


@dataclass(frozen=True)
class FrameworkAdapterDescriptor:
    key: str
    label: str
    language: str
    runner_family: str
    primary_use_cases: list[str]


class FutureAutomationFrameworkAdapter(ABC):
    @property
    @abstractmethod
    def descriptor(self) -> FrameworkAdapterDescriptor:
        raise NotImplementedError

    def to_dict(self) -> dict[str, Any]:
        desc = self.descriptor
        return {
            "key": desc.key,
            "label": desc.label,
            "language": desc.language,
            "runner_family": desc.runner_family,
            "primary_use_cases": list(desc.primary_use_cases),
        }


class PlaywrightAdapter(FutureAutomationFrameworkAdapter):
    @property
    def descriptor(self) -> FrameworkAdapterDescriptor:
        return FrameworkAdapterDescriptor(
            key="playwright",
            label="Playwright",
            language="TypeScript",
            runner_family="browser_ui",
            primary_use_cases=[
                "Web UI automation",
                "End-to-end business flow automation",
                "Cross-browser testing",
                "Visual evidence capture",
            ],
        )


class PytestAdapter(FutureAutomationFrameworkAdapter):
    @property
    def descriptor(self) -> FrameworkAdapterDescriptor:
        return FrameworkAdapterDescriptor(
            key="pytest",
            label="pytest",
            language="Python",
            runner_family="service_api",
            primary_use_cases=[
                "API automation",
                "Service and integration testing",
                "Database validation",
                "Contract and data-driven validation",
            ],
        )


SUPPORTED_FRAMEWORK_ADAPTERS: dict[str, FutureAutomationFrameworkAdapter] = {
    "playwright": PlaywrightAdapter(),
    "pytest": PytestAdapter(),
}


def supported_framework_catalog() -> list[dict[str, Any]]:
    return [adapter.to_dict() for adapter in SUPPORTED_FRAMEWORK_ADAPTERS.values()]


def framework_language(framework: str) -> str:
    adapter = SUPPORTED_FRAMEWORK_ADAPTERS.get((framework or "").lower())
    return adapter.descriptor.language if adapter else "Unknown"


def _text_blob(test_case: Any) -> str:
    values = [
        _read_value(test_case, "title", ""),
        _read_value(test_case, "test_type", ""),
        _read_value(test_case, "expected_result", ""),
        _read_value(test_case, "bdd_scenario", ""),
        _read_value(test_case, "telecom_domain", ""),
        _read_value(test_case, "product", ""),
        _read_value(test_case, "product_group", ""),
    ]
    steps = _read_value(test_case, "steps", []) or []
    for step in steps:
        if isinstance(step, dict):
            values.append(str(step.get("action", "")))
            values.append(str(step.get("expected_result", "")))
        else:
            values.append(str(step))
    return " ".join(str(value) for value in values if value).lower()


def _ui_signal_score(test_case: Any, text: str) -> int:
    score = 0
    steps = _read_value(test_case, "steps", []) or []
    if steps:
        score += 18
    if _read_value(test_case, "bdd_scenario"):
        score += 10
    if any(keyword in text for keyword in ["ui", "screen", "page", "portal", "browser", "form", "click", "button", "customer journey", "workflow", "journey", "visual", "web"]):
        score += 22
    if any(keyword in text for keyword in ["cross-browser", "responsive", "viewport", "frontend"]):
        score += 8
    return score


def _service_signal_score(test_case: Any, text: str) -> int:
    score = 0
    test_type = str(_read_value(test_case, "test_type", "") or "").lower()
    if any(keyword in test_type for keyword in ["api", "service", "integration", "database", "backend", "contract"]):
        score += 24
    if any(keyword in text for keyword in ["api", "endpoint", "request", "response", "payload", "schema", "database", "sql", "service", "contract", "validation", "backend"]):
        score += 24
    if any(keyword in text for keyword in ["data-driven", "parameterized", "fixture"]):
        score += 8
    return score


def assess_framework_fit(test_case: Any) -> dict[str, Any]:
    text = _text_blob(test_case)
    playwright_score = 20 + _ui_signal_score(test_case, text)
    pytest_score = 20 + _service_signal_score(test_case, text)

    execution_mode = str(_read_value(test_case, "execution_mode", "") or "").lower()
    if execution_mode == "hybrid":
        playwright_score += 8
        pytest_score += 8
    elif execution_mode == "automated":
        playwright_score += 4
        pytest_score += 4

    automation_ready = bool(_read_value(test_case, "automation_ready", False))
    if automation_ready:
        playwright_score += 6
        pytest_score += 6

    recommended = "playwright" if playwright_score >= pytest_score else "pytest"
    secondary = "pytest" if recommended == "playwright" else "playwright"
    hybrid_ready = abs(playwright_score - pytest_score) <= 10

    reasons: list[str] = []
    if recommended == "playwright":
        reasons.append("Structured user-flow steps favor browser automation.")
        if hybrid_ready:
            reasons.append("Service-level validation signals are also present, so a hybrid suite is viable.")
    else:
        reasons.append("API, service, or data-validation signals favor backend-oriented automation.")
        if hybrid_ready:
            reasons.append("UI-style journey steps are present, so Playwright can complement runner coverage.")

    if automation_ready:
        reasons.append("Test case is already marked automation-ready.")
    if _read_value(test_case, "priority", "") in {"High", "Critical"}:
        reasons.append("Priority is elevated, which supports repeatable automated coverage.")

    return {
        "recommended_framework": recommended,
        "secondary_framework": secondary,
        "hybrid_ready": hybrid_ready,
        "framework_scores": {
            "playwright": min(playwright_score, 100),
            "pytest": min(pytest_score, 100),
        },
        "reasons": reasons,
    }


def suitability_assessment(test_case: Any) -> dict[str, Any]:
    score = 35
    reasons: list[str] = []

    if str(_read_value(test_case, "status", "")).lower() == "approved":
        score += 15
        reasons.append("Approved test case is eligible for generation workflow.")
    if str(_read_value(test_case, "automation_eligible", "")).lower() == "yes":
        score += 12
        reasons.append("Marked automation-eligible in the test case library.")
    if bool(_read_value(test_case, "automation_ready", False)):
        score += 10
        reasons.append("Automation-ready flag reduces setup ambiguity.")
    if _read_value(test_case, "steps"):
        score += 8
        reasons.append("Structured steps exist for deterministic scripting.")
    if _read_value(test_case, "bdd_scenario"):
        score += 6
        reasons.append("BDD/business-flow text improves generation context.")
    if _read_value(test_case, "last_automation_status") == "failed":
        score -= 8
        reasons.append("Historical automation failure suggests maintenance risk.")

    score = max(0, min(score, 100))
    if score >= 75:
        band = "high"
    elif score >= 55:
        band = "medium"
    else:
        band = "low"

    return {
        "score": score,
        "band": band,
        "reasons": reasons,
    }
