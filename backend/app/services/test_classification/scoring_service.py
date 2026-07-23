"""Configurable weighted-factor scoring — same "factor + weight + score,
clamped 0..100" shape as coverage_service.py::_priority_score, generalized
into a reusable helper so weights come from the resolved policy's
`scoring_weights` instead of being embedded in this module or the UI.
"""
from __future__ import annotations

from app.services.test_classification.context import ClassificationContext

DEFAULT_AUTOMATION_VALUE_WEIGHTS: dict[str, int] = {
    "expected_result_determinism": 25,
    "regression_value": 20,
    "reusability": 15,
    "manual_effort": 20,
    "business_criticality": 20,
}

DEFAULT_COMPLEXITY_WEIGHTS: dict[str, int] = {
    "step_count": 30,
    "external_dependency_count": 30,
    "test_data_volume": 20,
    "precondition_count": 20,
}


def _weighted_score(factors: list[tuple[str, int, int]]) -> tuple[int, list[dict]]:
    """factors: list of (name, weight, raw_score_0_100). Returns
    (overall_score_0_100, breakdown)."""
    total_weight = sum(weight for _, weight, _ in factors) or 1
    weighted_sum = sum(weight * raw for _, weight, raw in factors)
    score = round(weighted_sum / (total_weight * 100) * 100)
    score = max(0, min(100, score))
    breakdown = [
        {"factor": name, "weight": weight, "score": round(weight * raw / 100)} for name, weight, raw in factors
    ]
    return score, breakdown


def _determinism_score(ctx: ClassificationContext) -> int:
    tc = ctx.test_case
    if tc.expected_result and tc.expected_result.strip() and tc.steps:
        return 100
    if tc.expected_result and tc.expected_result.strip():
        return 60
    return 20


def _regression_value_score(ctx: ClassificationContext) -> int:
    severity_scores = {"critical": 100, "high": 80, "medium": 50, "low": 25}
    return severity_scores.get((ctx.test_case.severity or "").lower(), 40)


def _reusability_score(ctx: ClassificationContext) -> int:
    return 80 if ctx.test_case.test_suite_id else 45


def _manual_effort_score(ctx: ClassificationContext) -> int:
    step_count = len(ctx.test_case.steps or [])
    return max(0, min(100, step_count * 10))


def _business_criticality_score(ctx: ClassificationContext) -> int:
    priority_scores = {"high": 100, "medium": 55, "low": 25}
    score = priority_scores.get((ctx.test_case.priority or "").lower(), 40)
    if ctx.requirement is not None:
        if ctx.requirement.regulatory_impact:
            score = min(100, score + 10)
        if ctx.requirement.revenue_impact:
            score = min(100, score + 10)
    return score


def _step_count_score(ctx: ClassificationContext) -> int:
    return max(0, min(100, len(ctx.test_case.steps or []) * 8))


def _external_dependency_score(mandatory_count: int, optional_count: int) -> int:
    return max(0, min(100, (mandatory_count * 20) + (optional_count * 10)))


def _test_data_volume_score(ctx: ClassificationContext) -> int:
    return max(0, min(100, len(ctx.test_case.test_data or {}) * 15))


def _precondition_score(ctx: ClassificationContext) -> int:
    return max(0, min(100, len(ctx.test_case.preconditions or []) * 15))


def compute_scores(
    ctx: ClassificationContext, *, mandatory_validator_count: int, optional_validator_count: int
) -> tuple[int, int, list[dict]]:
    """Returns (complexity_score, automation_value_score, combined factor breakdown)."""
    weights = (ctx.policy.rules or {}).get("scoring_weights") or {}
    av_weights = {**DEFAULT_AUTOMATION_VALUE_WEIGHTS, **(weights.get("automation_value") or {})}
    cx_weights = {**DEFAULT_COMPLEXITY_WEIGHTS, **(weights.get("complexity") or {})}

    av_factors = [
        ("expected_result_determinism", av_weights["expected_result_determinism"], _determinism_score(ctx)),
        ("regression_value", av_weights["regression_value"], _regression_value_score(ctx)),
        ("reusability", av_weights["reusability"], _reusability_score(ctx)),
        ("manual_effort", av_weights["manual_effort"], _manual_effort_score(ctx)),
        ("business_criticality", av_weights["business_criticality"], _business_criticality_score(ctx)),
    ]
    automation_value_score, av_breakdown = _weighted_score(av_factors)

    cx_factors = [
        ("step_count", cx_weights["step_count"], _step_count_score(ctx)),
        (
            "external_dependency_count",
            cx_weights["external_dependency_count"],
            _external_dependency_score(mandatory_validator_count, optional_validator_count),
        ),
        ("test_data_volume", cx_weights["test_data_volume"], _test_data_volume_score(ctx)),
        ("precondition_count", cx_weights["precondition_count"], _precondition_score(ctx)),
    ]
    complexity_score, cx_breakdown = _weighted_score(cx_factors)

    for item in av_breakdown:
        item["category"] = "automation_value"
    for item in cx_breakdown:
        item["category"] = "complexity"

    return complexity_score, automation_value_score, av_breakdown + cx_breakdown
