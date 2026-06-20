"""
Coverage gap detection & risk-based prioritization (GAP-4d).

Deterministic analytics — no LLM calls. Computes, per requirement:
  - linked scenario / test case counts
  - test-type mix vs. an expected coverage policy
  - missing coverage categories (gaps)
  - a coverage score (0-100)
  - a risk-based priority score (0-100) from requirement risk metadata

Used by /requirements/{id}/coverage and /requirements/project/{id}/coverage-summary.
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_scenario import TestScenario

# Coverage policy: categories every requirement is expected to have at least
# one test case for. test_type values come from the test case agent prompt:
# functional | negative | boundary | security | performance | usability | integration
EXPECTED_COVERAGE_CATEGORIES: dict[str, list[str]] = {
    "positive": ["functional", "positive"],
    "negative": ["negative"],
    "boundary": ["boundary"],
    "regression": ["regression"],
}

_RISK_WEIGHTS = {"critical": 40, "high": 30, "medium": 20, "low": 10}


def _priority_score(req: Requirement, coverage_score: float) -> tuple[int, str]:
    """Risk-based priority: higher = test first."""
    score = _RISK_WEIGHTS.get((req.risk_level or "").lower(), 15)
    if req.regulatory_impact:
        score += 20
    if req.revenue_impact:
        score += 20
    if req.customer_impact:
        score += 10
    # Uncovered risk amplifier: high-risk requirements with poor coverage rank first
    score += round((100 - coverage_score) * 0.10)
    score = max(0, min(100, score))
    band = "P1" if score >= 70 else "P2" if score >= 45 else "P3" if score >= 25 else "P4"
    return score, band


async def get_requirement_coverage(db: AsyncSession, req: Requirement) -> dict:
    """Full coverage detail for a single requirement."""
    scenario_count_res = await db.execute(
        select(func.count()).where(TestScenario.requirement_id == req.id)
    )
    scenario_count = scenario_count_res.scalar_one()

    type_rows = await db.execute(
        select(TestCase.test_type, func.count())
        .where(TestCase.requirement_id == req.id)
        .group_by(TestCase.test_type)
    )
    by_type: dict[str, int] = {}
    total_cases = 0
    for test_type, count in type_rows.all():
        key = (test_type or "unspecified").lower()
        by_type[key] = by_type.get(key, 0) + count
        total_cases += count

    automation_res = await db.execute(
        select(func.count()).where(
            TestCase.requirement_id == req.id,
            TestCase.automation_candidate.is_(True),
        )
    )
    automation_candidates = automation_res.scalar_one()

    covered: list[str] = []
    missing: list[str] = []
    for category, aliases in EXPECTED_COVERAGE_CATEGORIES.items():
        if any(by_type.get(alias, 0) > 0 for alias in aliases):
            covered.append(category)
        else:
            missing.append(category)

    gaps: list[str] = []
    if total_cases == 0:
        gaps.append("No test cases are linked to this requirement.")
    if scenario_count == 0:
        gaps.append("No test scenarios have been generated for this requirement.")
    for category in missing:
        gaps.append(f"No {category} test cases found.")
    ac_count = len(req.acceptance_criteria or [])
    if ac_count == 0:
        gaps.append("Requirement has no acceptance criteria — coverage cannot be validated against AC.")
    elif total_cases > 0 and total_cases < ac_count:
        gaps.append(
            f"Only {total_cases} test case(s) for {ac_count} acceptance criteria — some criteria may be untested."
        )

    coverage_score = round(100 * len(covered) / len(EXPECTED_COVERAGE_CATEGORIES)) if total_cases else 0
    priority_score, priority_band = _priority_score(req, coverage_score)

    return {
        "requirement_id": req.id,
        "requirement_key": req.requirement_id,
        "title": req.title,
        "quality_score": req.quality_score,
        "quality_verdict": req.quality_verdict,
        "risk_level": req.risk_level,
        "regulatory_impact": bool(req.regulatory_impact),
        "revenue_impact": bool(req.revenue_impact),
        "customer_impact": bool(req.customer_impact),
        "scenario_count": scenario_count,
        "test_case_count": total_cases,
        "automation_candidates": automation_candidates,
        "acceptance_criteria_count": ac_count,
        "cases_by_type": by_type,
        "covered_categories": covered,
        "missing_categories": missing,
        "coverage_score": coverage_score,
        "gaps": gaps,
        "priority_score": priority_score,
        "priority_band": priority_band,
    }


async def get_project_coverage_summary(db: AsyncSession, project_id: int, limit: int = 200) -> dict:
    """Coverage + priority overview for all requirements in a project,
    ordered by priority (test-first recommendation)."""
    reqs_res = await db.execute(
        select(Requirement)
        .where(Requirement.project_id == project_id, Requirement.is_deleted.is_(False))
        .order_by(Requirement.id)
        .limit(limit)
    )
    reqs = list(reqs_res.scalars().all())
    if not reqs:
        return {"project_id": project_id, "requirements": [], "summary": {
            "total_requirements": 0, "fully_covered": 0, "partially_covered": 0,
            "uncovered": 0, "avg_coverage_score": 0,
        }}

    req_ids = [r.id for r in reqs]

    # Aggregate scenario counts in one query
    sc_rows = await db.execute(
        select(TestScenario.requirement_id, func.count())
        .where(TestScenario.requirement_id.in_(req_ids))
        .group_by(TestScenario.requirement_id)
    )
    scenario_counts = dict(sc_rows.all())

    # Aggregate case counts by type in one query
    tc_rows = await db.execute(
        select(TestCase.requirement_id, TestCase.test_type, func.count())
        .where(TestCase.requirement_id.in_(req_ids))
        .group_by(TestCase.requirement_id, TestCase.test_type)
    )
    cases_by_req: dict[int, dict[str, int]] = {}
    for rid, test_type, count in tc_rows.all():
        bucket = cases_by_req.setdefault(rid, {})
        key = (test_type or "unspecified").lower()
        bucket[key] = bucket.get(key, 0) + count

    items = []
    fully = partial = uncovered = 0
    score_sum = 0
    for r in reqs:
        by_type = cases_by_req.get(r.id, {})
        total_cases = sum(by_type.values())
        covered = [
            cat for cat, aliases in EXPECTED_COVERAGE_CATEGORIES.items()
            if any(by_type.get(a, 0) > 0 for a in aliases)
        ]
        missing = [cat for cat in EXPECTED_COVERAGE_CATEGORIES if cat not in covered]
        coverage_score = round(100 * len(covered) / len(EXPECTED_COVERAGE_CATEGORIES)) if total_cases else 0
        priority_score, priority_band = _priority_score(r, coverage_score)

        if total_cases == 0:
            uncovered += 1
        elif missing:
            partial += 1
        else:
            fully += 1
        score_sum += coverage_score

        items.append({
            "requirement_id": r.id,
            "requirement_key": r.requirement_id,
            "title": r.title,
            "status": r.status,
            "quality_score": r.quality_score,
            "quality_verdict": r.quality_verdict,
            "risk_level": r.risk_level,
            "scenario_count": scenario_counts.get(r.id, 0),
            "test_case_count": total_cases,
            "covered_categories": covered,
            "missing_categories": missing,
            "coverage_score": coverage_score,
            "priority_score": priority_score,
            "priority_band": priority_band,
        })

    items.sort(key=lambda x: x["priority_score"], reverse=True)
    return {
        "project_id": project_id,
        "requirements": items,
        "summary": {
            "total_requirements": len(reqs),
            "fully_covered": fully,
            "partially_covered": partial,
            "uncovered": uncovered,
            "avg_coverage_score": round(score_sum / len(reqs)),
        },
    }
