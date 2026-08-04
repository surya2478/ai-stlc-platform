"""Celery tasks for dispatching AI agent runs asynchronously."""
from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from app.agents.automation.automation_agent import AutomationScriptAgent
from app.agents.automation.dry_run_agent import DryRunAgent
from app.agents.automation.eligibility_agent import AutomationEligibilityAgent
from app.agents.automation.grounded_capture_agent import GroundedCaptureAgent
from app.agents.automation.mcp_discovery_agent import PlaywrightMCPDiscoveryAgent
from app.agents.automation.planner_agent import PlaywrightPlannerAgent
from app.agents.execution.failure_classification_agent import FailureClassificationAgent
from app.agents.automation.repair_agent import RepairLoopAgent
from app.agents.automation.script_review_agent import AutomationScriptReviewAgent
from app.agents.defect.defect_agent import DefectAnalysisAgent
from app.agents.execution.execution_agent import TestExecutionAgent
from app.agents.reporting.reporting_agent import TestReportingAgent
from app.agents.requirement.enrichment_agent import RequirementEnrichmentAgent
from app.agents.requirement.intake_agent import RequirementIntakeAgent
from app.agents.requirement.quality_agent import RequirementQualityAgent
from app.agents.requirement.code_analysis_agent import CodeAnalysisAgent
from app.agents.requirement.ui_analysis_agent import UIAnalysisAgent
from app.agents.requirement.url_analysis_agent import URLAnalysisAgent
from app.agents.test_planning.planning_agent import TestPlanningAgent
from app.agents.test_planning.scenario_agent import TestScenarioAgent
from app.agents.test_planning.scenario_review_agent import ScenarioReviewAgent
from app.agents.test_classification.classification_agent import TestClassificationAgent
from app.agents.test_planning.test_case_agent import TestCaseDevelopmentAgent
from app.agents.test_planning.test_case_review_agent import TestCaseReviewAgent
from app.database import AsyncSessionLocal
from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.defect import DefectDraft
from app.models.document import UploadedDocument
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.project_application import ProjectApplication
from app.models.report import Report
from app.models.requirement import Requirement
from app.models.requirement_review import RequirementQualityReview
from app.models.test_case import TestCase
from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.llm.provider import (
    LLMRouteOverride,
    reset_llm_role_route_overrides,
    reset_llm_route_override,
    set_llm_role_route_overrides,
    set_llm_route_override,
)
from app.llm.roles import role_for_scope
from app.services import agent_progress, agent_run_service
from app.services import artifact_review_service
from app.services import automation_service
from app.services import coverage_matrix_service
from app.services import locator_catalog, locator_map_service
from app.services import navigation_map
from app.services import static_quality_gate
from app.services.script_compiler import locator_policy
from app.services import requirement_service
from app.services.display_id_service import display_id, temporary_id
from app.services.project_application_service import resolve_default_application, resolve_environment_url
from app.services.taxonomy_resolver import TaxonomyResolver, resolve_generated_test_case_taxonomy
from app.services.test_classification import classification_service
from app.services.project_llm_settings_service import list_settings, resolve_project_llm_routes
from app.services import traceability_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

# The band an agent's own progress is scaled into. Below it sits the wrapper's
# "Worker started" (10) and "Agent execution started" (30); above it,
# "Persisting agent result" (90). Keeping the agent inside 30-90 means its
# narration never contradicts those milestones.
_AGENT_PROGRESS_FLOOR = 30
_AGENT_PROGRESS_CEILING = 90

# A run in one of these has already been decided; re-executing it can only
# duplicate work or overwrite a result someone has already acted on.
_TERMINAL_AGENT_STATUSES = frozenset({"completed", "failed", "cancelled"})

AgentCallable = Callable[[dict[str, Any]], Awaitable[Any]]


class PermanentAgentError(Exception):
    """Non-retryable agent failure."""


class TransientAgentError(Exception):
    """Retryable agent failure."""


async def _requirement_intake(input_data: dict[str, Any]) -> Any:
    return await RequirementIntakeAgent().run(
        document_text=input_data["document_text"],
        project_id=input_data["project_id"],
    )


async def _requirement_quality(input_data: dict[str, Any]) -> Any:
    return await RequirementQualityAgent().run(requirements=input_data["requirements"])


async def _requirement_enrichment(input_data: dict[str, Any]) -> Any:
    return await RequirementEnrichmentAgent().run(
        requirements=input_data["requirements"],
        project_id=input_data.get("project_id", 0),
    )


async def _resolve_navigation_map(project_id: int) -> dict:
    """What this project already knows about where its navigation goes.

    Resolved here rather than inside the agent so the agents stay
    database-free, matching how every other input reaches them. A failure to
    build the map must not fail the analysis — the agent simply falls back to
    declaring destinations unknown, which is the behaviour it had before.
    """
    if not project_id:
        return {}
    try:
        async with AsyncSessionLocal() as db:
            return await navigation_map.resolve(db, project_id)
    except Exception:
        logger.exception("Could not build the navigation map for project %s", project_id)
        return {}


async def _ui_image_analysis(input_data: dict[str, Any]) -> Any:
    project_id = input_data.get("project_id", 0)
    return await UIAnalysisAgent().run(
        image_path=input_data["image_path"],
        image_name=input_data.get("image_name", "screenshot"),
        context_note=input_data.get("context_note", ""),
        project_id=project_id,
        # A screenshot has no hrefs. Anything this project has already read from
        # the live application is the only way the agent can resolve a
        # navigation target instead of asking a person for it.
        navigation=await _resolve_navigation_map(project_id),
    )


async def _url_analysis(input_data: dict[str, Any]) -> Any:
    project_id = input_data.get("project_id", 0)
    return await URLAnalysisAgent().run(
        url=input_data["url"],
        crawl_depth=input_data.get("crawl_depth", 0),
        context_note=input_data.get("context_note", ""),
        project_id=project_id,
        # This agent reads its own page's links, but a multi-page site's targets
        # may have been observed on a page it is not currently rendering.
        navigation=await _resolve_navigation_map(project_id),
    )


async def _code_analysis(input_data: dict[str, Any]) -> Any:
    """GAP-3: GitHub / local repo code analysis."""
    return await CodeAnalysisAgent().run(
        source=input_data["source"],
        project_id=input_data.get("project_id", 0),
        source_label=input_data.get("source_label", "github_repo"),
        github_url=input_data.get("github_url"),
        github_branch=input_data.get("github_branch", "main"),
        github_token=input_data.get("github_token"),
        github_subpath=input_data.get("github_subpath"),
        local_path=input_data.get("local_path"),
        languages=input_data.get("languages", ["python", "javascript", "typescript"]),
    )


async def _test_planning(input_data: dict[str, Any]) -> Any:
    return await TestPlanningAgent().run(
        requirements=input_data["requirements"],
        project_name=input_data.get("project_name", "Project"),
    )


async def _test_scenario(input_data: dict[str, Any]) -> Any:
    return await TestScenarioAgent().run(requirements=input_data["requirements"])


async def _scenario_review(input_data: dict[str, Any]) -> Any:
    return await ScenarioReviewAgent().run(
        requirements=input_data["requirements"],
        scenarios=input_data["scenarios"],
    )


async def _test_case(input_data: dict[str, Any]) -> Any:
    return await TestCaseDevelopmentAgent().run(scenarios=input_data["scenarios"])


async def _test_case_review(input_data: dict[str, Any]) -> Any:
    return await TestCaseReviewAgent().run(
        scenarios=input_data["scenarios"],
        test_cases=input_data["test_cases"],
    )


async def _automation_eligibility(input_data: dict[str, Any]) -> Any:
    return await AutomationEligibilityAgent().run(test_cases=input_data["test_cases"])


async def _playwright_mcp_discovery(input_data: dict[str, Any]) -> Any:
    return await PlaywrightMCPDiscoveryAgent().run(test_cases=input_data["test_cases"])


async def _playwright_planner(input_data: dict[str, Any]) -> Any:
    return await PlaywrightPlannerAgent().run(
        application_id=input_data.get("application_id"),
        application_url=input_data.get("application_url", ""),
        environment=input_data.get("environment"),
        objective=input_data.get("objective", ""),
        coverage_types=input_data.get("coverage_types"),
        excluded_paths=input_data.get("excluded_paths"),
        max_pages=input_data.get("max_pages", 10),
        max_minutes=input_data.get("max_minutes", 20),
        target_test_case_count=input_data.get("target_test_case_count"),
    )


async def _grounded_capture(input_data: dict[str, Any]) -> Any:
    return await GroundedCaptureAgent().run(
        test_case=input_data.get("test_case") or {},
        application_url=input_data.get("application_url", ""),
        application_id=input_data.get("application_id"),
        environment=input_data.get("environment"),
        capture_mode=input_data.get("capture_mode", "automated"),
        routing=input_data.get("routing"),
        confirmed_actions=input_data.get("confirmed_actions"),
    )


async def _automation_script(input_data: dict[str, Any]) -> Any:
    return await AutomationScriptAgent().run(
        test_cases=input_data["test_cases"],
        framework=input_data.get("framework", "playwright"),
        locator_map=input_data.get("locator_map"),
    )


async def _automation_dry_run(input_data: dict[str, Any]) -> Any:
    return await DryRunAgent().run(scripts=input_data["scripts"])


async def _failure_classification(input_data: dict[str, Any]) -> Any:
    return await FailureClassificationAgent().run(results=input_data["results"])


async def _automation_repair_loop(input_data: dict[str, Any]) -> Any:
    return await RepairLoopAgent().run(scripts=input_data["scripts"])


async def _automation_script_review(input_data: dict[str, Any]) -> Any:
    return await AutomationScriptReviewAgent().run(scripts=input_data["scripts"])


async def _test_execution(input_data: dict[str, Any]) -> Any:
    return await TestExecutionAgent().run(
        test_cases=input_data["test_cases"],
        environment=input_data.get("environment", "local"),
        suite_name=input_data.get("suite_name", "Agent Test Suite"),
        source_type=input_data.get("source_type", "manual"),
    )


async def _defect_analysis(input_data: dict[str, Any]) -> Any:
    return await DefectAnalysisAgent().run(
        failed_results=input_data["failed_results"],
        project_name=input_data.get("project_name", "Project"),
    )


async def _test_classification(input_data: dict[str, Any]) -> Any:
    return await TestClassificationAgent().run(
        test_case=input_data.get("test_case") or {},
        requirement=input_data.get("requirement"),
        scenario=input_data.get("scenario"),
        application=input_data.get("application"),
        policy_rules=input_data.get("policy_rules") or {},
        deterministic_blockers=input_data.get("deterministic_blockers") or [],
        deterministic_warnings=input_data.get("deterministic_warnings") or [],
        routing_default_adapter=input_data.get("routing_default_adapter"),
        routing_default_mandatory_validators=input_data.get("routing_default_mandatory_validators") or [],
        routing_default_optional_validators=input_data.get("routing_default_optional_validators") or [],
        agent_enabled=input_data.get("agent_enabled", True),
    )


async def _test_reporting(input_data: dict[str, Any]) -> Any:
    return await TestReportingAgent().run(
        metrics=input_data["metrics"],
        project_name=input_data.get("project_name", "Project"),
        report_type=input_data.get("report_type", "summary"),
    )


AGENT_REGISTRY: dict[str, AgentCallable] = {
    "requirement_intake": _requirement_intake,
    "requirement_quality": _requirement_quality,
    "requirement_enrichment": _requirement_enrichment,
    "ui_image_analysis": _ui_image_analysis,
    "url_analysis": _url_analysis,
    "code_analysis": _code_analysis,
    "test_planning": _test_planning,
    "test_scenario": _test_scenario,
    "scenario_review": _scenario_review,
    "test_case": _test_case,
    "test_case_review": _test_case_review,
    "automation_eligibility": _automation_eligibility,
    "playwright_mcp_discovery": _playwright_mcp_discovery,
    "playwright_planner": _playwright_planner,
    "grounded_capture": _grounded_capture,
    "automation_script": _automation_script,
    "automation_dry_run": _automation_dry_run,
    "failure_classification": _failure_classification,
    "automation_repair_loop": _automation_repair_loop,
    "automation_script_review": _automation_script_review,
    "test_execution": _test_execution,
    "defect_analysis": _defect_analysis,
    "test_reporting": _test_reporting,
    "test_classification": _test_classification,
}


@dataclass(frozen=True)
class AgentSpec:
    """Per-agent execution policy (Phase 0 foundation hardening).

    Looked up by agent_name via `get_agent_spec`; any agent_name not present in
    `AGENT_SPECS` (e.g. an ad-hoc name used in tests) falls back to
    `DEFAULT_AGENT_SPEC` rather than raising, so this is purely additive over
    `AGENT_REGISTRY` — it does not change how agents are invoked.
    """

    timeout_seconds: float = 120.0
    retry_policy: str = "default"  # default | none | aggressive
    chain_on_success: tuple[str, ...] = ()
    module_scope: str | None = None
    # Explicit LLM role pin. Only needed when an agent's module_scope maps to
    # the "wrong" role via SCOPE_ROLE_MAP (e.g. test_planning's own scope is
    # shared with the coding-role scenario/test-case agents, but planning
    # itself is a reasoning task). Leave unset to inherit from module_scope.
    llm_role: str | None = None


DEFAULT_AGENT_SPEC = AgentSpec()


def agent_role(agent_name: str) -> str:
    spec = get_agent_spec(agent_name)
    return spec.llm_role or role_for_scope(spec.module_scope)

# Timeouts reflect real observed cost: LLM-only generators stay near the
# original 120s default, while multi-call agents get more headroom. Requirement
# intake can make several sequential model calls for a single document and has
# been observed exceeding 120s even when every call succeeds.
# Reviewer/MCP-grounded agents added in later phases should be registered here
# with their own timeout rather than relying on the default.
AGENT_SPECS: dict[str, AgentSpec] = {
    "requirement_intake": AgentSpec(timeout_seconds=300.0, module_scope="requirement"),
    "requirement_quality": AgentSpec(timeout_seconds=180.0, module_scope="requirement_review"),
    "requirement_enrichment": AgentSpec(timeout_seconds=120.0, module_scope="requirement"),
    "ui_image_analysis": AgentSpec(timeout_seconds=180.0, module_scope="requirement"),
    "url_analysis": AgentSpec(timeout_seconds=240.0, module_scope="requirement"),
    "code_analysis": AgentSpec(timeout_seconds=240.0, module_scope="requirement"),
    # Explicit reasoning pin: module_scope="test_planning" is shared with the
    # scenario/test-case generator agents below (which correctly inherit
    # "coding" from SCOPE_ROLE_MAP), but planning itself is a reasoning task.
    "test_planning": AgentSpec(timeout_seconds=180.0, module_scope="test_planning", llm_role="reasoning"),
    "test_scenario": AgentSpec(
        timeout_seconds=180.0, module_scope="test_planning", chain_on_success=("scenario_review",)
    ),
    "scenario_review": AgentSpec(timeout_seconds=180.0, module_scope="scenario_review"),
    "test_case": AgentSpec(
        timeout_seconds=180.0, module_scope="test_planning", chain_on_success=("test_case_review",)
    ),
    "test_case_review": AgentSpec(
        timeout_seconds=180.0, module_scope="test_case_review", chain_on_success=("automation_eligibility",)
    ),
    # Fans out to both: discovery grounds the test cases whose application has
    # a resolvable URL, and generation picks up only the ones discovery will
    # not touch (see _build_automation_script_input). Disjoint sets, so an
    # ungrounded script is never generated for an application that could have
    # been discovered first.
    "automation_eligibility": AgentSpec(
        timeout_seconds=60.0, module_scope="automation_eligibility",
        chain_on_success=("playwright_mcp_discovery", "automation_script"),
    ),
    # Auto-chained since Phase 5 — was deliberately manual-only in Phase 3
    # (discovery spawns a real browser session against a live environment).
    # Kept safe by _build_mcp_discovery_input only firing for test cases
    # whose application already has a real, resolvable environment URL
    # (skips silently otherwise) — it never guesses or spawns against a
    # placeholder. The manual "Discover UI" trigger (POST /agent/discover-ui)
    # still exists for re-running discovery on demand (e.g. after a UI change).
    # Chains into generation so a discovered test case gets a *grounded*
    # script without anyone clicking Generate: by the time this completes,
    # the locator map build_generation_payload reads is populated.
    "playwright_mcp_discovery": AgentSpec(
        timeout_seconds=450.0, module_scope="mcp_discovery",
        chain_on_success=("automation_script",),
    ),
    # Playwright AI Studio's exploration+planning agent: a bounded BFS crawl
    # (max 25 pages) with one LLM proposal call per page. The generous cap
    # covers slow SIT environments; the agent's own max_minutes budget
    # usually ends the crawl well before this. Deliberately NOT chained —
    # its output is a *proposal* that must pass the bulk plan-approval gate
    # (studio_service.approve_plan) before anything else runs.
    "playwright_planner": AgentSpec(timeout_seconds=1800.0, module_scope="playwright_studio"),
    # Grounded Automation PoC: a TC-guided browser walk — no LLM calls in
    # the walk itself, but real page loads against a live environment, so
    # the timeout matches the agent's own max_minutes budget (20m) + slack.
    # Deliberately NOT chained: its output must pass the deterministic
    # coverage gate and an explicit user Generate action before anything
    # else runs (grounded_poc_service.start_generation).
    "grounded_capture": AgentSpec(timeout_seconds=1500.0, module_scope="grounded_poc"),
    # 240s was sized for a human generating scripts for a handful of
    # approved test cases; Playwright AI Studio submits waves of up to 25 at
    # once. AutomationScriptAgent now fans generation out with bounded
    # concurrency (automation_agent.GENERATION_CONCURRENCY=5) instead of
    # running test cases one at a time, but 900s stays as a real ceiling —
    # concurrency shrinks wall-clock time, it doesn't guarantee a hard cap
    # when every LLM call in a wave needs multiple corrective retries.
    # Fans out to both: automation_dry_run only picks up scripts the static
    # gate passed ("static_passed"); automation_repair_loop only picks up
    # scripts the gate blocked ("generated" + a failed static_gate_result) —
    # see _build_dry_run_input and _build_gate_repair_input. Disjoint sets,
    # so every generated script reaches exactly one of the two.
    "automation_script": AgentSpec(
        timeout_seconds=900.0, module_scope="automation",
        chain_on_success=("automation_dry_run", "automation_repair_loop"),
    ),
    # Same wave-sizing rationale as automation_script — DryRunAgent also
    # fans out with bounded concurrency (DRY_RUN_CONCURRENCY=5) now, but
    # each dry run is a real subprocess (Node+Chromium), so the ceiling
    # stays generous.
    "automation_dry_run": AgentSpec(
        timeout_seconds=900.0, module_scope="automation_dry_run",
        # Failed dry-runs go to classification/repair; passed ones (the only
        # scripts the plan allows reviewers to see) go straight to review.
        chain_on_success=("failure_classification", "automation_script_review"),
    ),
    "failure_classification": AgentSpec(
        timeout_seconds=90.0, module_scope="failure_classification",
        chain_on_success=("automation_repair_loop",),
    ),
    # Up to MAX_REPAIR_ATTEMPTS (3) full patch->compile->gate->dry-run
    # cycles per script — and Studio batches hand it SEVERAL failing scripts
    # in one run (observed live 2026-07-11: 600s expired mid-loop on a
    # 6-script Studio batch, killing repairs that were converging). Budget
    # scales with the worst case: ~3 attempts x ~60-90s dry run x several
    # scripts.
    "automation_repair_loop": AgentSpec(
        timeout_seconds=1800.0, module_scope="automation_repair_loop",
        chain_on_success=("automation_script_review",),
    ),
    "automation_script_review": AgentSpec(timeout_seconds=180.0, module_scope="automation_script_review"),
    "test_execution": AgentSpec(timeout_seconds=300.0, module_scope="execution"),
    "defect_analysis": AgentSpec(timeout_seconds=180.0, module_scope="defect"),
    "test_reporting": AgentSpec(timeout_seconds=180.0, module_scope="reporting"),
    # Not auto-chained after test_case/test_case_review — classification is
    # explicitly triggered per test case (UI-010 Classify/Reclassify row
    # action), not implied by generation.
    "test_classification": AgentSpec(timeout_seconds=90.0, module_scope="test_classification"),
}


def get_agent_spec(agent_name: str) -> AgentSpec:
    return AGENT_SPECS.get(agent_name, DEFAULT_AGENT_SPEC)


# Chain-input builders, keyed by the *child* agent_name. `chain_on_success` on
# an AgentSpec only names the next agent(s) to run; a builder here maps the
# parent's (db, run, input_data, output_data) into the child's input_data,
# since that mapping is agent-pair-specific and can't be inferred
# generically. Builders are async and receive `db` because the parent's
# `output_data` only carries persisted row IDs — building a reviewer's input
# means fetching the full rows back out (see _build_scenario_review_input).
ChainInputBuilder = Callable[[Any, AgentRun, dict[str, Any], dict[str, Any]], Awaitable[dict[str, Any] | None]]
CHAIN_INPUT_BUILDERS: dict[str, ChainInputBuilder] = {}


async def _build_scenario_review_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    scenario_ids = output_data.get("scenario_ids") or []
    requirements = input_data.get("requirements") or []
    if not scenario_ids or not requirements:
        return None
    result = await db.execute(select(TestScenario).where(TestScenario.id.in_(scenario_ids)))
    scenarios = [
        {
            "id": s.id,
            "scenario_id": s.scenario_id,
            "title": s.title,
            "description": s.description,
            "scenario_type": s.scenario_type,
            "priority": s.priority,
            "coverage_mapping": s.coverage_mapping or [],
            "_source_requirement_id": s.requirement_id,
        }
        for s in result.scalars().all()
    ]
    if not scenarios:
        return None
    return {"requirements": requirements, "scenarios": scenarios}


async def _build_test_case_review_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    tc_ids = output_data.get("test_case_ids") or []
    scenarios = input_data.get("scenarios") or []
    if not tc_ids or not scenarios:
        return None
    result = await db.execute(select(TestCase).where(TestCase.id.in_(tc_ids)))
    test_cases = [
        {
            "id": tc.id,
            "test_case_id": tc.test_case_id,
            "title": tc.title,
            "preconditions": tc.preconditions or [],
            "steps": tc.steps or [],
            "expected_result": tc.expected_result,
            "priority": tc.priority,
            "test_type": tc.test_type,
            "_source_scenario_id": tc.scenario_id,
        }
        for tc in result.scalars().all()
    ]
    if not test_cases:
        return None
    return {"scenarios": scenarios, "test_cases": test_cases}


async def _build_automation_eligibility_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    # test_case_review's own input already carries the full test case dicts
    # (see _build_test_case_review_input) — no DB re-fetch needed.
    test_cases = input_data.get("test_cases") or []
    if not test_cases:
        return None
    return {"test_cases": test_cases}


async def _build_mcp_discovery_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Auto-chain discovery for newly-eligible test cases whose application
    already has a real, resolvable environment URL.

    This reverses an earlier deliberate decision to keep discovery
    exclusively manual (it spawns a real browser session against a live
    environment). Kept safe by only firing when a URL is actually
    resolvable — silently skipping any test case whose application isn't
    configured yet, same as every other "nothing to do" case in this file —
    so it never spawns a browser at a guessed or placeholder URL. Multiple
    test cases across multiple applications in one batch are all passed
    into a single discovery run; the agent already groups them internally
    by application_id (see mcp_discovery_agent.run's `by_application` split).
    """
    tc_ids = output_data.get("test_case_ids") or []
    if not tc_ids:
        return None
    result = await db.execute(select(TestCase).where(TestCase.id.in_(tc_ids)))
    test_cases = []
    for tc in result.scalars().all():
        if tc.project_id != run.project_id or tc.automation_eligible != "yes":
            continue
        application = None
        if tc.application_id:
            application = await db.get(ProjectApplication, tc.application_id)
        if application is None:
            application = await resolve_default_application(db, run.project_id)
        if application is None:
            continue
        environment = tc.test_phase or "QA"
        application_url = resolve_environment_url(application, environment)
        if not application_url:
            continue  # no URL configured for this environment — nothing to discover against
        test_cases.append({
            "id": tc.id,
            "test_case_id": tc.test_case_id,
            "title": tc.title,
            "steps": tc.steps or [],
            "application_id": application.id,
            "application_url": application_url,
        })
    if not test_cases:
        return None
    return {"test_cases": test_cases}


async def _build_automation_script_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Auto-chain script generation, so a test case classified eligible does
    not sit at `ready_for_automation` with no script until a human clicks
    Generate on it one at a time.

    Generation was the only stage in this pipeline that never advanced on its
    own: nothing named `automation_script` in a `chain_on_success`, so the
    chain ran to discovery and stopped. Two test cases with identical status
    would differ only in whether somebody had visited the workspace for them.

    Wired to BOTH parents deliberately, because ordering decides whether the
    script is grounded:

      * after `playwright_mcp_discovery` — the normal path. Discovery has
        already written locator evidence, so `build_generation_payload`
        returns a populated locator map and the script is grounded.
      * after `automation_eligibility` — only for test cases discovery will
        NOT pick up (no resolvable environment URL). Chaining both parents
        unconditionally would race: generation could start before discovery
        finished and silently produce ungrounded scripts for applications
        that do have a URL.

    Idempotent by construction: a test case that already has a script is
    skipped, so a re-run of either parent never produces a duplicate.
    """
    from app.services.automation_generation_service import build_generation_payload

    # `automation_eligibility` reports the ids it classified; discovery does
    # not, but its own input carried the cases. Which key is present is what
    # tells us which parent we were chained from.
    eligibility_ids = list(output_data.get("test_case_ids") or [])
    if eligibility_ids:
        tc_ids = eligibility_ids
        # Leave anything discovery will handle to the discovery-chained call.
        discovery_input = await _build_mcp_discovery_input(db, run, input_data, output_data)
        deferred = {tc["id"] for tc in (discovery_input or {}).get("test_cases", [])}
        tc_ids = [tc_id for tc_id in tc_ids if tc_id not in deferred]
    else:
        tc_ids = [tc["id"] for tc in input_data.get("test_cases", []) if tc.get("id")]
    if not tc_ids:
        return None

    existing = (
        await db.execute(
            select(AutomationScript.test_case_id).where(
                AutomationScript.project_id == run.project_id,
                AutomationScript.test_case_id.in_(tc_ids),
            )
        )
    ).scalars().all()
    tc_ids = [tc_id for tc_id in tc_ids if tc_id not in set(existing)]
    if not tc_ids:
        return None

    # Same payload builder the manual endpoint uses, so the chained path and
    # the button cannot drift apart — including its "approved only" filter.
    payload = await build_generation_payload(
        db, project_id=run.project_id, test_case_ids=tc_ids
    )
    if not payload.test_cases:
        return None
    return {
        "test_cases": payload.test_cases,
        "framework": "playwright",
        "locator_map": payload.locator_map,
    }


async def _build_dry_run_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    script_ids = output_data.get("script_ids") or []
    if not script_ids:
        return None
    result = await db.execute(select(AutomationScript).where(AutomationScript.id.in_(script_ids)))
    tc_by_db_id = {tc.get("id"): tc for tc in input_data.get("test_cases", [])}
    scripts = []
    for script in result.scalars().all():
        if script.status != "static_passed" or script.project_id != run.project_id:
            continue  # only dry-run scripts the static gate actually passed
        tc = tc_by_db_id.get(script.test_case_id) or {}
        scripts.append({
            "script_id": script.id,
            "framework": script.framework,
            "file_path": script.file_path,
            "compiled_files": script.compiled_files,
            "execution_command": script.execution_command,
            "application_url": tc.get("application_url"),
            "environment": tc.get("test_phase") or tc.get("test_environment") or "QA",
        })
    if not scripts:
        return None
    return {"scripts": scripts}


async def _build_failure_classification_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    result = await db.execute(
        select(ExecutionResult)
        .join(ExecutionRun, ExecutionResult.execution_run_id == ExecutionRun.id)
        .where(ExecutionRun.agent_run_id == run.id, ExecutionResult.status != "pass")
    )
    rows = result.scalars().all()
    if not rows:
        return None
    results = [
        {
            "result_id": r.id,
            "status": r.status,
            "error_message": r.error_message,
            "stack_trace": r.stack_trace,
            "console_logs": (r.metadata_ or {}).get("console_logs"),
            "network_logs": (r.metadata_ or {}).get("network_logs"),
        }
        for r in rows
    ]
    return {"results": results}


async def _build_repair_loop_input_from_classification(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    classified_ids = output_data.get("classified_result_ids") or []
    if not classified_ids:
        return None
    result = await db.execute(select(ExecutionResult).where(ExecutionResult.id.in_(classified_ids)))

    scripts = []
    for exec_result in result.scalars().all():
        classification_info = (exec_result.metadata_ or {}).get("failure_classification") or {}
        if not classification_info.get("repairable"):
            continue
        automation_script_id = (exec_result.metadata_ or {}).get("automation_script_id")
        if not automation_script_id:
            continue
        script = await db.get(AutomationScript, automation_script_id)
        if not script or not script.contract or script.project_id != run.project_id:
            continue

        application_url = None
        environment = "QA"
        catalog: list[dict] = []
        tc = await db.get(TestCase, script.test_case_id) if script.test_case_id else None
        if tc:
            environment = tc.test_phase or "QA"
            application = await db.get(ProjectApplication, tc.application_id) if tc.application_id else None
            if application is None:
                application = await resolve_default_application(db, run.project_id)
            if application:
                application_url = resolve_environment_url(application, environment)
                built = await locator_catalog.build_for_application(
                    db, project_id=run.project_id, application_id=application.id
                )
                catalog = [
                    {
                        "element_name": entry["element_name"],
                        "recommended_locator": entry["recommended_locator"],
                        "business_meaning": entry["business_meaning"],
                    }
                    for entry in built.entries
                ]

        scripts.append({
            "script_id": script.id,
            "contract": script.contract,
            "framework": script.framework,
            "application_url": application_url,
            "environment": environment,
            "locator_catalog": catalog,
            "failure": {
                "classification": classification_info.get("classification"),
                "error_message": exec_result.error_message,
                "stack_trace": exec_result.stack_trace,
            },
        })

    if not scripts:
        return None
    return {"scripts": scripts}


# Codes the Static Quality Gate stamps deterministically for any valid
# contract the Script Compiler actually ran (see static_quality_gate.py's
# _check_generation_header / _check_tc_req_mapping). If either is missing,
# the contract isn't the problem -- no LLM-proposed patch changes that --
# so these are left for manual regeneration instead of burning a repair
# attempt on them.
_GATE_CODES_NOT_REPAIRABLE = {"missing_generation_header", "missing_tc_req_mapping"}


async def _build_gate_repair_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Static-gate failures never produce a dry run (_build_dry_run_input
    only picks up status == "static_passed") and so never reach
    failure_classification either -- without this, a script whose gate
    failed right after generation just sat at status "generated" forever
    with no automatic next step. Feeds the gate's own violations to
    RepairLoopAgent as the failure evidence, the same contract-patch loop a
    dry-run failure already uses."""
    script_ids = output_data.get("script_ids") or []
    if not script_ids:
        return None
    result = await db.execute(select(AutomationScript).where(AutomationScript.id.in_(script_ids)))
    tc_by_db_id = {tc.get("id"): tc for tc in input_data.get("test_cases", [])}
    locator_map = input_data.get("locator_map") or {}

    scripts = []
    for script in result.scalars().all():
        if script.status != "generated" or script.project_id != run.project_id or not script.contract:
            continue
        gate = script.static_gate_result or {}
        if gate.get("passed") is not False:
            continue  # only scripts the static gate actually blocked
        violations = gate.get("violations") or []
        fixable_codes = {v.get("code") for v in violations} - _GATE_CODES_NOT_REPAIRABLE
        if not fixable_codes:
            continue

        tc = tc_by_db_id.get(script.test_case_id) or {}
        raw_catalog = locator_map.get(str(tc.get("application_id"))) if tc.get("application_id") is not None else None
        catalog = locator_policy.filter_catalog_by_page(raw_catalog or [], tc.get("application_url")) or []

        scripts.append({
            "script_id": script.id,
            "contract": script.contract,
            "framework": script.framework,
            "application_url": tc.get("application_url"),
            "environment": tc.get("test_phase") or tc.get("test_environment") or "QA",
            "locator_catalog": catalog,
            "failure": {
                "classification": "static_gate_violation",
                "error_message": "; ".join(v.get("message", "") for v in violations) or "Static quality gate failed.",
                "stack_trace": None,
            },
        })

    if not scripts:
        return None
    return {"scripts": scripts}


async def _build_repair_loop_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    """Dispatches to whichever of the two repair-loop producers actually
    fired: failure_classification (a real dry-run failure classified as
    repairable) or automation_script (a static gate failure right after
    generation). Both name "automation_repair_loop" in chain_on_success, so
    the input builder — looked up by child agent name only, not by parent —
    must tell them apart from output_data's shape instead."""
    if "classified_result_ids" in output_data:
        return await _build_repair_loop_input_from_classification(db, run, input_data, output_data)
    if "script_ids" in output_data:
        return await _build_gate_repair_input(db, run, input_data, output_data)
    return None


async def _build_script_review_input(
    db, run: AgentRun, input_data: dict[str, Any], output_data: dict[str, Any]
) -> dict[str, Any] | None:
    # Reachable from two parents (automation_dry_run's "promoted_script_ids"
    # and automation_repair_loop's "resolved_script_ids") — both name only
    # dry_run_passed scripts, matching the plan's exit criterion that only
    # dry_run_passed scripts reach reviewers.
    script_ids = output_data.get("promoted_script_ids") or output_data.get("resolved_script_ids") or []
    if not script_ids:
        return None
    result = await db.execute(select(AutomationScript).where(AutomationScript.id.in_(script_ids)))
    scripts = []
    for script in result.scalars().all():
        if script.project_id != run.project_id:
            continue
        tc = await db.get(TestCase, script.test_case_id) if script.test_case_id else None
        last_dry_run = (script.metadata_ or {}).get("last_dry_run") or {"passed": True}
        scripts.append({
            "script_id": script.id,
            "test_case": {
                "test_case_id": tc.test_case_id if tc else None,
                "title": tc.title if tc else None,
                "preconditions": tc.preconditions if tc else [],
                "steps": tc.steps if tc else [],
                "expected_result": tc.expected_result if tc else None,
            } if tc else {},
            "code": script.code,
            "static_gate_result": script.static_gate_result,
            "dry_run_evidence": last_dry_run,
        })
    if not scripts:
        return None
    return {"scripts": scripts}


CHAIN_INPUT_BUILDERS["scenario_review"] = _build_scenario_review_input
CHAIN_INPUT_BUILDERS["test_case_review"] = _build_test_case_review_input
CHAIN_INPUT_BUILDERS["automation_eligibility"] = _build_automation_eligibility_input
CHAIN_INPUT_BUILDERS["playwright_mcp_discovery"] = _build_mcp_discovery_input
CHAIN_INPUT_BUILDERS["automation_script"] = _build_automation_script_input
CHAIN_INPUT_BUILDERS["automation_dry_run"] = _build_dry_run_input
CHAIN_INPUT_BUILDERS["failure_classification"] = _build_failure_classification_input
CHAIN_INPUT_BUILDERS["automation_repair_loop"] = _build_repair_loop_input
CHAIN_INPUT_BUILDERS["automation_script_review"] = _build_script_review_input


async def _chain_next_agents(
    db,
    run: AgentRun,
    agent_name: str,
    input_data: dict[str, Any],
    output_data: dict[str, Any] | None,
) -> None:
    """Enqueue any agents configured to run after `agent_name` completes.

    Isolated from the parent run's outcome: a chaining failure is logged and
    skipped, never raised — the parent agent already completed successfully
    and that result must stand regardless of what happens downstream.
    """
    next_names = get_agent_spec(agent_name).chain_on_success
    if not next_names:
        return
    from app.services import agent_dispatch_service  # deferred: avoids import cycle

    for next_name in next_names:
        builder = CHAIN_INPUT_BUILDERS.get(next_name)
        if builder is None:
            logger.warning(
                "chain_on_success names '%s' after '%s' but no input builder is registered; skipping",
                next_name, agent_name,
            )
            continue
        try:
            chain_input = await builder(db, run, input_data, output_data or {})
            if chain_input is None:
                continue
            await agent_dispatch_service.enqueue_agent_run(
                db,
                project_id=run.project_id,
                user_id=run.triggered_by,
                agent_name=next_name,
                input_data=chain_input,
                metadata={"chained_from_run_id": run.id},
            )
            await db.commit()
        except Exception:
            logger.exception(
                "Failed to chain '%s' after agent run %s ('%s')", next_name, run.id, agent_name,
            )


def _is_success(agent_result: Any) -> bool:
    if hasattr(agent_result, "success"):
        return bool(agent_result.success)
    return getattr(agent_result, "status", None) == "completed"


def _result_data(agent_result: Any) -> dict[str, Any]:
    data = getattr(agent_result, "data", None)
    return data if isinstance(data, dict) else {}


def _to_text(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    import json
    return json.dumps(value)


def _to_list(value) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


async def _persist_agent_artifacts(
    db,
    run: AgentRun,
    agent_name: str,
    input_data: dict[str, Any],
    agent_result: Any,
) -> dict[str, Any] | None:
    data = _result_data(agent_result)
    if agent_name == "requirement_intake":
        created = []
        document_id = (run.metadata_ or {}).get("document_id")
        for req_data in data.get("requirements", []):
            req = Requirement(
                project_id=run.project_id,
                created_by=run.triggered_by,
                requirement_id=temporary_id("REQ"),
                source="doc_upload",
                title=req_data.get("title", "Untitled Requirement"),
                summary=req_data.get("summary"),
                acceptance_criteria=req_data.get("acceptance_criteria"),
                business_rules=req_data.get("business_rules"),
                user_roles=req_data.get("user_roles"),
                systems_impacted=req_data.get("systems_impacted"),
                ui_pages=req_data.get("ui_pages"),
                apis=req_data.get("apis"),
                dependencies=req_data.get("dependencies"),
                risks=req_data.get("risks"),
                missing_information=req_data.get("missing_information"),
                telecom_domain=req_data.get("telecom_domain"),
                impacted_interfaces=req_data.get("impacted_interfaces"),
                risk_level=req_data.get("risk_level"),
                test_phase=req_data.get("test_phase"),
                release_version=req_data.get("release_version"),
                regulatory_impact=bool(req_data.get("regulatory_impact", False)),
                revenue_impact=bool(req_data.get("revenue_impact", False)),
                source_document_id=document_id,
                status="draft",
                readiness_status="intake_ready",
                metadata_={"workflow_stage": "intake"},
            )
            db.add(req)
            await db.flush()
            req.requirement_id = display_id("REQ", req.id)
            await db.flush()
            if document_id:
                await traceability_service.create_lineage(
                    db,
                    project_id=run.project_id,
                    parent_type="uploaded_document",
                    parent_id=document_id,
                    child_type="requirement",
                    child_id=req.id,
                    agent_run_id=run.id,
                )
            created.append(req.id)
        return {"requirement_ids": created, "count": len(created)}

    if agent_name == "ui_image_analysis":
        # GAP-1: persist requirements derived from a UI screenshot. Downstream
        # agents (quality, scenario, test case) work on these unchanged.
        created = []
        document_id = (run.metadata_ or {}).get("document_id")
        ui_analysis = data.get("ui_analysis") or {}
        for req_data in data.get("requirements", []):
            req = Requirement(
                project_id=run.project_id,
                created_by=run.triggered_by,
                requirement_id=temporary_id("REQ"),
                source="ui_image",
                title=req_data.get("title", "Untitled Requirement"),
                summary=req_data.get("summary"),
                acceptance_criteria=req_data.get("acceptance_criteria"),
                business_rules=req_data.get("business_rules"),
                user_roles=req_data.get("user_roles"),
                systems_impacted=req_data.get("systems_impacted"),
                ui_pages=req_data.get("ui_pages"),
                apis=req_data.get("apis"),
                dependencies=req_data.get("dependencies"),
                risks=req_data.get("risks"),
                missing_information=req_data.get("missing_information"),
                telecom_domain=req_data.get("telecom_domain"),
                impacted_interfaces=req_data.get("impacted_interfaces"),
                risk_level=req_data.get("risk_level"),
                test_phase=req_data.get("test_phase"),
                regulatory_impact=bool(req_data.get("regulatory_impact", False)),
                revenue_impact=bool(req_data.get("revenue_impact", False)),
                source_document_id=document_id,
                status="draft",
                readiness_status="intake_ready",
                metadata_={
                    "workflow_stage": "intake",
                    "input_kind": "ui_image",
                    "ui_analysis": {
                        "screen_name": ui_analysis.get("screen_name"),
                        "screen_purpose": ui_analysis.get("screen_purpose"),
                        "fields": ui_analysis.get("fields", []),
                        "buttons": ui_analysis.get("buttons", []),
                        "links": ui_analysis.get("links", []),
                        "user_flows": ui_analysis.get("user_flows", []),
                        "validation_rules": ui_analysis.get("validation_rules", []),
                        "negative_scenarios": ui_analysis.get("negative_scenarios", []),
                        "edge_cases": ui_analysis.get("edge_cases", []),
                    },
                },
            )
            db.add(req)
            await db.flush()
            req.requirement_id = display_id("REQ", req.id)
            await db.flush()
            if document_id:
                await traceability_service.create_lineage(
                    db,
                    project_id=run.project_id,
                    parent_type="uploaded_document",
                    parent_id=document_id,
                    child_type="requirement",
                    child_id=req.id,
                    agent_run_id=run.id,
                )
            created.append(req.id)
        return {"requirement_ids": created, "count": len(created)}

    if agent_name == "url_analysis":
        # GAP-2: persist portal-URL analysis — one UploadedDocument (page
        # screenshot snapshot) per captured page, plus derived requirements
        # with source="portal_url". Downstream agents work on these unchanged.
        created = []
        documents = []
        source_url = data.get("source_url")
        for page in data.get("pages", []):
            doc = None
            if page.get("screenshot_path"):
                doc = UploadedDocument(
                    project_id=run.project_id,
                    created_by=run.triggered_by,
                    original_filename=f"{(page.get('title') or 'page')[:80]}.png",
                    stored_filename=page.get("screenshot_name") or "url_capture.png",
                    file_path=page["screenshot_path"],
                    file_type="png",
                    file_size_bytes=page.get("screenshot_size") or 0,
                    status="processed",
                    metadata_={"input_kind": "url_capture", "source_url": page.get("url")},
                )
                db.add(doc)
                await db.flush()
                documents.append(doc.id)

            ui_analysis = page.get("ui_analysis") or {}
            for req_data in page.get("requirements", []):
                req = Requirement(
                    project_id=run.project_id,
                    created_by=run.triggered_by,
                    requirement_id=temporary_id("REQ"),
                    source="portal_url",
                    title=req_data.get("title", "Untitled Requirement"),
                    summary=req_data.get("summary"),
                    acceptance_criteria=req_data.get("acceptance_criteria"),
                    business_rules=req_data.get("business_rules"),
                    user_roles=req_data.get("user_roles"),
                    systems_impacted=req_data.get("systems_impacted"),
                    ui_pages=req_data.get("ui_pages"),
                    apis=req_data.get("apis"),
                    dependencies=req_data.get("dependencies"),
                    risks=req_data.get("risks"),
                    missing_information=req_data.get("missing_information"),
                    telecom_domain=req_data.get("telecom_domain"),
                    impacted_interfaces=req_data.get("impacted_interfaces"),
                    risk_level=req_data.get("risk_level"),
                    test_phase=req_data.get("test_phase"),
                    regulatory_impact=bool(req_data.get("regulatory_impact", False)),
                    revenue_impact=bool(req_data.get("revenue_impact", False)),
                    source_document_id=doc.id if doc else None,
                    status="draft",
                    readiness_status="intake_ready",
                    metadata_={
                        "workflow_stage": "intake",
                        "input_kind": "portal_url",
                        "source_url": page.get("url"),
                        "ui_analysis": {
                            "screen_name": ui_analysis.get("screen_name"),
                            "screen_purpose": ui_analysis.get("screen_purpose"),
                            "fields": ui_analysis.get("fields", []),
                            "buttons": ui_analysis.get("buttons", []),
                            "links": ui_analysis.get("links", []),
                            "user_flows": ui_analysis.get("user_flows", []),
                            "validation_rules": ui_analysis.get("validation_rules", []),
                            "negative_scenarios": ui_analysis.get("negative_scenarios", []),
                            "edge_cases": ui_analysis.get("edge_cases", []),
                        },
                    },
                )
                db.add(req)
                await db.flush()
                req.requirement_id = display_id("REQ", req.id)
                await db.flush()
                if doc:
                    await traceability_service.create_lineage(
                        db,
                        project_id=run.project_id,
                        parent_type="uploaded_document",
                        parent_id=doc.id,
                        child_type="requirement",
                        child_id=req.id,
                        agent_run_id=run.id,
                    )
                created.append(req.id)
        return {
            "requirement_ids": created,
            "document_ids": documents,
            "count": len(created),
            "source_url": source_url,
        }

    if agent_name == "code_analysis":
        # GAP-3: persist requirements derived from GitHub / local repo source code.
        created = []
        source_label = data.get("source_label", "github_repo")  # "github_repo" | "local_repo"
        repo_url = data.get("repo_url")
        local_path = data.get("local_path")
        for req_data in data.get("requirements", []):
            req = Requirement(
                project_id=run.project_id,
                created_by=run.triggered_by,
                requirement_id=temporary_id("REQ"),
                source=source_label,
                title=req_data.get("title", "Untitled Requirement"),
                summary=req_data.get("summary"),
                acceptance_criteria=req_data.get("acceptance_criteria"),
                business_rules=req_data.get("business_rules"),
                user_roles=req_data.get("user_roles"),
                systems_impacted=req_data.get("systems_impacted"),
                apis=req_data.get("apis"),
                risks=req_data.get("risks"),
                telecom_domain=req_data.get("telecom_domain"),
                risk_level=req_data.get("risk_level"),
                test_phase=req_data.get("test_phase"),
                status="draft",
                readiness_status="intake_ready",
                metadata_={
                    "workflow_stage": "intake",
                    "input_kind": source_label,
                    "repo_url": repo_url,
                    "local_path": local_path,
                    "source_file": req_data.get("source_file"),
                    "file_count": data.get("file_count"),
                },
            )
            db.add(req)
            await db.flush()
            req.requirement_id = display_id("REQ", req.id)
            await db.flush()
            created.append(req.id)
        return {"requirement_ids": created, "count": len(created), "source": source_label}

    if agent_name == "requirement_quality":
        # GAP-4a fix: previously this agent's output was silently dropped.
        # Persist quality reviews to RequirementQualityReview, denormalise onto
        # Requirement, and mirror a compact summary into metadata_ for the UI.
        quality_data: dict = data.get("quality_results", {}) or {}
        updated_ids: list[int] = []
        review_mode = await artifact_review_service.get_review_mode(db, run.project_id)
        for str_id, qr in quality_data.items():
            try:
                req_id = int(str_id)
            except (ValueError, TypeError):
                continue
            if not qr:
                continue
            result = await db.execute(select(Requirement).where(Requirement.id == req_id))
            req = result.scalar_one_or_none()
            if not req or req.project_id != run.project_id:
                continue

            overall = qr.get("overall_score")
            verdict = qr.get("verdict")
            scenario_readiness = qr.get("scenario_generation_readiness")

            feedback_parts = []
            if qr.get("issues"):
                feedback_parts.append("Issues: " + "; ".join(qr["issues"][:3]))
            if qr.get("suggestions"):
                feedback_parts.append("Suggestions: " + "; ".join(qr["suggestions"][:2]))
            feedback = " | ".join(feedback_parts) if feedback_parts else None

            await requirement_service.update_quality_scores(
                db, req,
                quality_score=overall,
                quality_feedback=feedback,
                quality_verdict=verdict,
                scenario_generation_readiness=scenario_readiness,
            )

            # Compact summary in metadata_ — the Requirements UI reads
            # metadata_.quality_review for the quality badge.
            metadata = dict(req.metadata_ or {})
            metadata["quality_review"] = {
                "overall_score": overall,
                "verdict": verdict,
                "scenario_generation_readiness": scenario_readiness,
                "scores": {
                    "completeness": qr.get("completeness_score"),
                    "clarity": qr.get("clarity_score"),
                    "testability": qr.get("testability_score"),
                    "ambiguity": qr.get("ambiguity_score"),
                    "acceptance_criteria": qr.get("acceptance_criteria_score"),
                    "interface_readiness": qr.get("interface_readiness_score"),
                    "telecom_domain_completeness": qr.get("telecom_domain_completeness"),
                },
                "findings": qr.get("issues", []),
                "recommendations": qr.get("suggestions", []),
                "pass_score": 3.5,
                "pass_scenario_readiness": 3,
                "stale": False,
                "agent_run_id": run.id,
            }
            req.metadata_ = metadata

            review = RequirementQualityReview(
                requirement_id=req.id,
                project_id=run.project_id,
                created_by=run.triggered_by,
                quality_score=overall,
                verdict=verdict,
                completeness_score=qr.get("completeness_score"),
                clarity_score=qr.get("clarity_score"),
                testability_score=qr.get("testability_score"),
                ambiguity_score=qr.get("ambiguity_score"),
                acceptance_criteria_score=qr.get("acceptance_criteria_score"),
                interface_readiness_score=qr.get("interface_readiness_score"),
                # live DB column is qa_domain_completeness
                qa_domain_completeness=qr.get("telecom_domain_completeness"),
                scenario_generation_readiness=scenario_readiness,
                ambiguities=qr.get("issues", []),
                missing_details=[],
                recommendations=qr.get("suggestions", []),
                clarification_questions=[],
                status="completed",
                agent_run_id=run.id,
            )
            db.add(review)
            await db.flush()

            # Phase 1: also write the generic ArtifactReview row so this stage
            # shares one review/badge surface with scenario_review and
            # test_case_review, rather than the requirement-only table above.
            await artifact_review_service.create_review(
                db,
                project_id=run.project_id,
                agent_run_id=run.id,
                artifact_type="requirement",
                artifact_id=req.id,
                reviewer_agent="requirement_quality",
                scores={
                    "completeness": qr.get("completeness_score"),
                    "clarity": qr.get("clarity_score"),
                    "testability": qr.get("testability_score"),
                    "ambiguity": qr.get("ambiguity_score"),
                    "acceptance_criteria": qr.get("acceptance_criteria_score"),
                    "interface_readiness": qr.get("interface_readiness_score"),
                    "telecom_domain_completeness": qr.get("telecom_domain_completeness"),
                    "scenario_generation_readiness": scenario_readiness,
                },
                overall_score=overall,
                verdict=verdict,
                findings=[{"dimension": "issue", "issue": i} for i in qr.get("issues", [])]
                + [{"dimension": "suggestion", "issue": s} for s in qr.get("suggestions", [])],
                coverage_gaps=None,
                review_mode=review_mode,
            )
            updated_ids.append(req.id)
        return {"requirement_ids": updated_ids, "count": len(updated_ids)}

    if agent_name == "requirement_enrichment":
        # GAP-4b: enrich Jira-imported requirements with structured fields from
        # the intake agent. Only fills fields that are currently empty — never
        # overwrites user edits or Jira sync data.
        enriched_ids: list[int] = []
        list_fields = (
            "acceptance_criteria", "business_rules", "user_roles", "systems_impacted",
            "ui_pages", "apis", "dependencies", "risks", "missing_information",
            "impacted_interfaces", "upstream_systems", "downstream_systems",
        )
        scalar_fields = ("telecom_domain", "risk_level", "test_phase", "release_version")
        for item in data.get("enriched_requirements", []):
            req_id = item.get("id")
            fields = item.get("fields") or {}
            if not req_id or not fields:
                continue
            result = await db.execute(select(Requirement).where(Requirement.id == req_id))
            req = result.scalar_one_or_none()
            if not req or req.project_id != run.project_id:
                continue
            changed = False
            for f in list_fields:
                if not getattr(req, f, None) and fields.get(f):
                    setattr(req, f, fields[f])
                    changed = True
            for f in scalar_fields:
                if not getattr(req, f, None) and fields.get(f):
                    setattr(req, f, fields[f])
                    changed = True
            for f in ("regulatory_impact", "revenue_impact"):
                if getattr(req, f, None) is not True and fields.get(f) is True:
                    setattr(req, f, True)
                    changed = True
            if changed:
                metadata = dict(req.metadata_ or {})
                metadata["enriched_by_intake_agent"] = True
                req.metadata_ = metadata
                await db.flush()
                enriched_ids.append(req.id)
        return {"requirement_ids": enriched_ids, "count": len(enriched_ids)}

    if agent_name == "test_planning":
        plan_data = data.get("test_plan") or {}
        plan = TestPlan(
            project_id=run.project_id,
            created_by=run.triggered_by,
            test_plan_id=temporary_id("TP"),
            title=plan_data.get("title", "Test Plan"),
            scope=plan_data.get("scope"),
            out_of_scope=plan_data.get("out_of_scope"),
            test_types=plan_data.get("test_types"),
            entry_criteria=plan_data.get("entry_criteria"),
            exit_criteria=plan_data.get("exit_criteria"),
            risks=plan_data.get("risks"),
            mitigations=plan_data.get("mitigations"),
            automation_candidates=plan_data.get("automation_candidates"),
            estimated_effort=_to_text(plan_data.get("estimated_effort")),
            resource_recommendation=_to_text(plan_data.get("resource_recommendation")),
            status="draft",
            agent_run_id=run.id,
            metadata_={"source_requirement_ids": (run.metadata_ or {}).get("approved_requirement_ids", [])},
        )
        db.add(plan)
        await db.flush()
        plan.test_plan_id = display_id("TP", plan.id)
        await db.flush()
        await traceability_service.create_lineage_many(
            db,
            project_id=run.project_id,
            parents=[("requirement", rid) for rid in (run.metadata_ or {}).get("approved_requirement_ids", [])],
            child_type="test_plan",
            child_id=plan.id,
            agent_run_id=run.id,
        )
        return {"plan_id": plan.id, "test_plan_id": plan.test_plan_id}

    if agent_name == "test_scenario":
        reqs = input_data.get("requirements", [])
        created = []
        for sc_data in data.get("scenarios", []):
            src = sc_data.get("_source_requirement_id")
            db_req_id = next((r["id"] for r in reqs if r.get("id") == src or r.get("requirement_id") == src), None)
            sc = TestScenario(
                project_id=run.project_id,
                requirement_id=db_req_id,
                created_by=run.triggered_by,
                scenario_id=temporary_id("TS"),
                title=sc_data.get("title", "Untitled Scenario"),
                description=sc_data.get("description"),
                scenario_type=sc_data.get("scenario_type", "positive"),
                priority=sc_data.get("priority", "Medium"),
                coverage_mapping=sc_data.get("coverage_mapping"),
                status="draft",
                agent_run_id=run.id,
            )
            db.add(sc)
            await db.flush()
            sc.scenario_id = display_id("TS", sc.id)
            await db.flush()
            if db_req_id:
                await traceability_service.create_lineage(
                    db,
                    project_id=run.project_id,
                    parent_type="requirement",
                    parent_id=db_req_id,
                    child_type="test_scenario",
                    child_id=sc.id,
                    agent_run_id=run.id,
                )
            created.append(sc.id)
        return {"scenario_ids": created, "count": len(created)}

    if agent_name == "scenario_review":
        # Phase 1: coverage-focused review of the requirement's *set* of
        # scenarios. input_data here is what _build_scenario_review_input
        # assembled — full requirement dicts + the persisted scenario rows.
        requirements = input_data.get("requirements", [])
        req_lookup: dict[str, int] = {}
        for r in requirements:
            rid = r.get("id")
            if rid is None:
                continue
            req_lookup[str(rid)] = rid
            if r.get("requirement_id"):
                req_lookup[r["requirement_id"]] = rid

        review_mode = await artifact_review_service.get_review_mode(db, run.project_id)
        created_ids = []
        for rv in data.get("reviews", []):
            req_id = req_lookup.get(rv.get("target_ref"))
            if req_id is None:
                continue
            review = await artifact_review_service.create_review(
                db,
                project_id=run.project_id,
                agent_run_id=run.id,
                artifact_type="requirement_scenario_coverage",
                artifact_id=req_id,
                reviewer_agent="scenario_review",
                scores=rv.get("scores"),
                overall_score=rv.get("overall_score"),
                verdict=rv.get("verdict", "needs_revision"),
                findings=rv.get("findings"),
                coverage_gaps=rv.get("coverage_gaps"),
                review_mode=review_mode,
            )
            created_ids.append(review.id)
        return {"review_ids": created_ids, "count": len(created_ids), "summary": data.get("summary")}

    if agent_name == "test_case":
        scenarios = input_data.get("scenarios", [])
        scenario_id_map = {s.get("scenario_id"): s.get("id") for s in scenarios}
        req_id_map = {s.get("id"): s.get("_source_requirement_id") for s in scenarios}
        # The endpoint stamps each scenario dict with the parent requirement's
        # Environment tag before enqueueing (see trigger_test_case_agent in
        # test_plans.py) — carry it through onto the created test case.
        env_map = {s.get("id"): s.get("test_environment") for s in scenarios}
        taxonomy_resolver = TaxonomyResolver(db)
        created = []
        for tc_data in data.get("test_cases", []):
            db_sc_id = scenario_id_map.get(tc_data.get("_source_scenario_id"))
            db_req_id = req_id_map.get(db_sc_id)
            taxonomy_fields = await resolve_generated_test_case_taxonomy(taxonomy_resolver, tc_data)
            tc = TestCase(
                project_id=run.project_id,
                scenario_id=db_sc_id,
                requirement_id=db_req_id,
                created_by=run.triggered_by,
                test_case_id=temporary_id("TC"),
                title=tc_data.get("title", "Untitled Test Case"),
                preconditions=tc_data.get("preconditions"),
                test_data=tc_data.get("test_data"),
                steps=tc_data.get("steps"),
                expected_result=tc_data.get("expected_result"),
                bdd_scenario=tc_data.get("bdd_scenario"),
                priority=tc_data.get("priority", "Medium"),
                severity=tc_data.get("severity", "Medium"),
                test_type=tc_data.get("test_type"),
                automation_candidate=bool(tc_data.get("automation_candidate", False)),
                test_phase=env_map.get(db_sc_id),
                status="draft",
                agent_run_id=run.id,
                **taxonomy_fields,
            )
            db.add(tc)
            await db.flush()
            tc.test_case_id = display_id("TC", tc.id)
            await db.flush()
            parents = []
            if db_sc_id:
                parents.append(("test_scenario", db_sc_id))
            if db_req_id:
                parents.append(("requirement", db_req_id))
            await traceability_service.create_lineage_many(
                db,
                project_id=run.project_id,
                parents=parents,
                child_type="test_case",
                child_id=tc.id,
                agent_run_id=run.id,
            )
            created.append(tc.id)
        return {"test_case_ids": created, "count": len(created)}

    if agent_name == "test_case_review":
        # Phase 1: coverage-focused review of the scenario's *set* of test
        # cases. Also seeds the coverage_matrix baseline row for every test
        # case under the reviewed scenario, since this is the first point in
        # the pipeline where a test case's full context (requirement,
        # scenario, case class) is all resolved together.
        scenarios = input_data.get("scenarios", [])
        scenario_lookup: dict[str, int] = {}
        scenario_type_by_id: dict[int, str | None] = {}
        for s in scenarios:
            sid = s.get("id")
            if sid is None:
                continue
            scenario_lookup[str(sid)] = sid
            if s.get("scenario_id"):
                scenario_lookup[s["scenario_id"]] = sid
            scenario_type_by_id[sid] = s.get("scenario_type")

        tc_ids_all = [tc.get("id") for tc in input_data.get("test_cases", []) if tc.get("id")]
        tc_rows: dict[int, TestCase] = {}
        if tc_ids_all:
            tc_result = await db.execute(select(TestCase).where(TestCase.id.in_(tc_ids_all)))
            tc_rows = {tc.id: tc for tc in tc_result.scalars().all()}

        review_mode = await artifact_review_service.get_review_mode(db, run.project_id)
        created_ids = []
        for rv in data.get("reviews", []):
            scenario_db_id = scenario_lookup.get(rv.get("target_ref"))
            if scenario_db_id is None:
                continue
            review = await artifact_review_service.create_review(
                db,
                project_id=run.project_id,
                agent_run_id=run.id,
                artifact_type="scenario_test_case_coverage",
                artifact_id=scenario_db_id,
                reviewer_agent="test_case_review",
                scores=rv.get("scores"),
                overall_score=rv.get("overall_score"),
                verdict=rv.get("verdict", "needs_revision"),
                findings=rv.get("findings"),
                coverage_gaps=rv.get("coverage_gaps"),
                review_mode=review_mode,
            )
            created_ids.append(review.id)

            case_class = coverage_matrix_service.case_class_from_scenario_type(
                scenario_type_by_id.get(scenario_db_id)
            )
            for tc in tc_rows.values():
                if tc.scenario_id == scenario_db_id:
                    await coverage_matrix_service.seed_from_test_case(
                        db, project_id=run.project_id, test_case=tc, case_class=case_class,
                    )
        return {"review_ids": created_ids, "count": len(created_ids), "summary": data.get("summary")}

    if agent_name == "automation_eligibility":
        # Phase 2.7: replaces the one-shot automation_candidate boolean with
        # an auditable verdict on TestCase + the coverage_matrix row seeded
        # by test_case_review.
        tc_lookup = {tc.get("test_case_id"): tc.get("id") for tc in input_data.get("test_cases", [])}
        status_by_verdict = {"yes": "ready_for_automation", "no": "not_required"}
        updated_ids: list[int] = []
        for result in data.get("results", []):
            db_tc_id = tc_lookup.get(result.get("test_case_id"))
            if not db_tc_id:
                continue
            tc = await db.get(TestCase, db_tc_id)
            if not tc or tc.project_id != run.project_id:
                continue
            verdict = result.get("verdict", "unknown")
            reason = result.get("reason", "")
            tc.automation_eligible = verdict
            if verdict in status_by_verdict:
                tc.automation_status = status_by_verdict[verdict]
            metadata = dict(tc.metadata_ or {})
            metadata["automation_eligibility"] = {
                "verdict": verdict,
                "reason": reason,
                "automation_style": result.get("automation_style"),
                "agent_run_id": run.id,
            }
            tc.metadata_ = metadata
            await coverage_matrix_service.record_eligibility(
                db, test_case_id=tc.id, automation_eligible=verdict, automation_reason=reason,
            )
            updated_ids.append(tc.id)
        return {"test_case_ids": updated_ids, "count": len(updated_ids), "summary": data.get("summary")}

    if agent_name == "playwright_mcp_discovery":
        # Phase 3.4/3.5/3.6: persist the durable locator knowledge base and
        # apply eligibility pass 2 (live-evidence overrides of the static
        # pass-1 guess from automation_eligibility).
        tc_lookup = {tc.get("test_case_id"): tc.get("id") for tc in input_data.get("test_cases", [])}
        # Every test case whose application was discovered is a parent of
        # every element discovered for that application — discovery grounds
        # the whole page, not one element per test case. Without this, the
        # Trace drawer had no way to show "this TC's automation was grounded
        # by discovery run X" (locator_map has no test_case_id column at all).
        tc_ids_by_application: dict[int, list[int]] = {}
        for tc in input_data.get("test_cases", []):
            app_id = tc.get("application_id")
            tc_db_id = tc.get("id")
            if app_id is not None and tc_db_id is not None:
                tc_ids_by_application.setdefault(app_id, []).append(tc_db_id)

        locator_ids: list[int] = []
        overridden_tc_ids: list[int] = []

        for app_result in data.get("applications", []):
            application_id = app_result.get("application_id")
            parent_tc_ids = tc_ids_by_application.get(application_id, [])
            for page in app_result.get("pages", []):
                page_url = page.get("url") or ""
                for element in page.get("elements", []):
                    entry = await locator_map_service.upsert_locator(
                        db,
                        project_id=run.project_id,
                        application_id=application_id,
                        page=page_url,
                        element_name=element["element_name"],
                        recommended_locator=element["recommended_locator"],
                        recommended_strategy=element["recommended_strategy"],
                        business_meaning=element.get("business_meaning"),
                        confidence_score=element.get("confidence_score", 0),
                    )
                    locator_ids.append(entry.id)
                    if parent_tc_ids:
                        await traceability_service.create_lineage_many(
                            db,
                            project_id=run.project_id,
                            parents=[("test_case", tc_id) for tc_id in parent_tc_ids],
                            child_type="locator_map",
                            child_id=entry.id,
                            agent_run_id=run.id,
                        )

            for tc_business_id, reasons in (app_result.get("eligibility_overrides") or {}).items():
                db_tc_id = tc_lookup.get(tc_business_id)
                if not db_tc_id:
                    continue
                tc = await db.get(TestCase, db_tc_id)
                if not tc or tc.project_id != run.project_id:
                    continue
                tc.automation_eligible = "no"
                tc.automation_status = "not_required"
                metadata = dict(tc.metadata_ or {})
                metadata["automation_eligibility_live_override"] = {
                    "reasons": reasons,
                    "agent_run_id": run.id,
                }
                tc.metadata_ = metadata
                await coverage_matrix_service.record_eligibility(
                    db, test_case_id=tc.id, automation_eligible="no",
                    automation_reason="Live discovery evidence: " + "; ".join(reasons),
                )
                overridden_tc_ids.append(tc.id)

        return {
            "locator_entry_ids": locator_ids,
            "count": len(locator_ids),
            "eligibility_overridden_test_case_ids": overridden_tc_ids,
        }

    if agent_name == "playwright_planner":
        # Playwright AI Studio: persist the explored element catalog into
        # locator_map (same knowledge base discovery feeds — generation
        # grounding reads it back via build_generation_payload) and hand the
        # proposed test plan to the StudioRun (exploring → plan_ready).
        # Proposals stay data on the run row until the bulk plan-approval
        # gate materializes them as TestCase rows.
        from app.services import studio_service

        application_id = data.get("application_id") or input_data.get("application_id")
        locator_ids: list[int] = []
        for page in data.get("pages", []):
            page_url = page.get("url") or ""
            for element in page.get("elements", []):
                entry = await locator_map_service.upsert_locator(
                    db,
                    project_id=run.project_id,
                    application_id=application_id,
                    page=page_url,
                    element_name=element["element_name"],
                    recommended_locator=element["recommended_locator"],
                    recommended_strategy=element["recommended_strategy"],
                    business_meaning=element.get("business_meaning"),
                    confidence_score=element.get("confidence_score", 0),
                )
                locator_ids.append(entry.id)

        studio_run_id = input_data.get("studio_run_id")
        if studio_run_id:
            await studio_service.apply_planner_output(
                db, studio_run_id=studio_run_id, agent_run=run, output=data
            )

        return {
            "locator_entry_ids": locator_ids,
            "count": len(locator_ids),
            "explored_page_count": data.get("explored_page_count", 0),
            "proposed_test_case_count": len(data.get("proposed_test_cases", [])),
            "studio_run_id": studio_run_id,
        }

    if agent_name == "grounded_capture":
        # Grounded Automation PoC: persist Application State Evidence
        # Packages and run the four-dimension coverage gate (or pause for
        # assisted-mode confirmation). Everything lives in poc_* tables —
        # no locator_map writes, no TestCase mutation.
        from app.services import grounded_poc_service

        grounding_run_id = input_data.get("grounding_run_id")
        if not grounding_run_id:
            logger.warning("grounded_capture output without grounding_run_id; dropping")
            return {"dropped": True}
        return await grounded_poc_service.apply_capture_output(
            db, grounding_run_id=grounding_run_id, agent_run=run, output=data
        )

    if agent_name == "automation_script":
        # Phase 2 (ADR-001): script_data.code is compiler output, not
        # free-form LLM text — script_data always carries `contract` (the
        # validated Automation Generation Contract) and `compiled_files`
        # (the full multi-file bundle). Status starts "generated" and the
        # Static Quality Gate runs immediately, before any human sees it.
        test_cases = input_data.get("test_cases", [])
        tc_map = {tc.get("test_case_id"): tc.get("id") for tc in test_cases}
        created = []
        for script_data in data.get("scripts", []):
            db_tc_id = tc_map.get(script_data.get("test_case_id"))
            script = AutomationScript(
                project_id=run.project_id,
                test_case_id=db_tc_id,
                created_by=run.triggered_by,
                script_id=temporary_id("AS"),
                framework=input_data.get("framework", "playwright"),
                file_path=_to_text(script_data.get("file_path")),
                code=_to_text(script_data.get("code")) or "",
                setup_required=_to_list(script_data.get("setup_required")),
                execution_command=_to_text(script_data.get("execution_command")),
                compiled_files=script_data.get("compiled_files"),
                contract=script_data.get("contract"),
                status="generated",
                agent_run_id=run.id,
                metadata_={
                    "source": "ai_generation",
                    "grounding": {
                        "grounded": script_data.get("grounded", False),
                        "grounded_element_count": script_data.get("grounded_element_count", 0),
                        "ungrounded_elements": script_data.get("ungrounded_elements", []),
                    },
                    # Every generation attempt (validation/grounding failures
                    # and the corrective retry that followed each), so a
                    # reviewer can see *why* a script needed N attempts
                    # instead of just the final result.
                    "generation_attempts": script_data.get("generation_attempts", []),
                },
            )
            db.add(script)
            await db.flush()
            script.script_id = display_id("AS", script.id)
            await db.flush()

            gate_result = static_quality_gate.run_static_quality_gate(script)
            script.static_gate_result = gate_result.as_dict()
            if gate_result.passed:
                script.status = "static_passed"

            if db_tc_id:
                await traceability_service.create_lineage(
                    db,
                    project_id=run.project_id,
                    parent_type="test_case",
                    parent_id=db_tc_id,
                    child_type="automation_script",
                    child_id=script.id,
                    agent_run_id=run.id,
                )
                await coverage_matrix_service.record_script_linked(
                    db, test_case_id=db_tc_id, script_id=script.id
                )
            created.append(script.id)
        return {"script_ids": created, "count": len(created)}

    if agent_name == "automation_dry_run":
        # Phase 4.2: one real subprocess execution per newly-generated
        # script, tagged source_type="dry_run" so it's distinguishable from
        # a human-triggered regression run. Promotion to "dry_run_passed"
        # only happens when every test in the script passed — anything else
        # stays at "static_passed" for failure_classification / the repair
        # loop (Phase 4.3/4.4) to pick up.
        promoted_ids: list[int] = []
        for dry_run in data.get("dry_runs", []):
            script = await db.get(AutomationScript, dry_run.get("script_id"))
            if not script or script.project_id != run.project_id:
                continue
            results = dry_run.get("results", [])
            exec_run = ExecutionRun(
                project_id=run.project_id,
                created_by=run.triggered_by,
                triggered_by=run.triggered_by,
                execution_id=temporary_id("ER"),
                environment="dry-run",
                execution_type="automation",
                source_type="dry_run",
                status="completed" if dry_run.get("run_status") == "completed" else "failed",
                total_tests=len(results),
                passed=sum(1 for r in results if r.get("status") == "pass"),
                failed=sum(1 for r in results if r.get("status") == "fail"),
                skipped=sum(1 for r in results if r.get("status") == "skip"),
                agent_run_id=run.id,
                metadata_={"automation_script_id": script.id, "dry_run": True},
            )
            db.add(exec_run)
            await db.flush()
            exec_run.execution_id = display_id("ER", exec_run.id)
            for r in results:
                db.add(ExecutionResult(
                    execution_run_id=exec_run.id,
                    test_case_id=script.test_case_id,
                    project_id=run.project_id,
                    test_name=r.get("name") or script.script_id,
                    status=r.get("status") or "error",
                    duration_ms=r.get("duration_ms"),
                    error_message=r.get("error_message"),
                    stack_trace=r.get("stack_trace"),
                    screenshot_path=r.get("screenshot_path"),
                    video_path=r.get("video_path"),
                    trace_path=r.get("trace_path"),
                    metadata_={
                        "automation_script_id": script.id,
                        "dry_run": True,
                        "console_logs": r.get("console_logs"),
                        "network_logs": r.get("network_logs"),
                    },
                ))
            await db.flush()

            metadata = dict(script.metadata_ or {})
            metadata["last_dry_run"] = {
                "execution_run_id": exec_run.id,
                "passed": dry_run.get("passed", False),
                "agent_run_id": run.id,
            }
            script.metadata_ = metadata
            if dry_run.get("passed"):
                script.status = "dry_run_passed"
                promoted_ids.append(script.id)

        return {"promoted_script_ids": promoted_ids, "count": len(promoted_ids)}

    if agent_name == "failure_classification":
        classified_ids: list[int] = []
        for c in data.get("classifications", []):
            exec_result = await db.get(ExecutionResult, c.get("result_id"))
            if not exec_result or exec_result.project_id != run.project_id:
                continue
            metadata = dict(exec_result.metadata_ or {})
            metadata["failure_classification"] = {
                "classification": c.get("classification"),
                "reason": c.get("reason"),
                "source": c.get("source"),
                "repairable": c.get("repairable", False),
                "agent_run_id": run.id,
            }
            exec_result.metadata_ = metadata
            classified_ids.append(exec_result.id)
        return {"classified_result_ids": classified_ids, "count": len(classified_ids)}

    if agent_name == "automation_repair_loop":
        # Phase 4.4: one new AutomationScript VERSION per attempt — see
        # automation_service.persist_repair_outcome (shared with the
        # on-demand "Repair script" trigger for real execution failures).
        resolved_ids: list[int] = []
        for repair in data.get("repairs", []):
            parent_script = await db.get(AutomationScript, repair.get("script_id"))
            if not parent_script or parent_script.project_id != run.project_id:
                continue
            last_version = await automation_service.persist_repair_outcome(
                db,
                project_id=run.project_id,
                triggered_by=run.triggered_by,
                agent_run_id=run.id,
                parent_script=parent_script,
                repair=repair,
            )
            if last_version is not None and repair.get("resolved"):
                resolved_ids.append(last_version.id)

        return {"resolved_script_ids": resolved_ids, "count": len(resolved_ids)}

    if agent_name == "automation_script_review":
        # Phase 4.5: senior-reviewer verdict per script version, on top of the
        # already-passed Static Quality Gate + dry run. Writes an
        # ArtifactReview only — it does NOT flip script.status itself; the
        # reviewer_approved/lead_approved transitions are human role-gated
        # (Task 42) and merely informed by this verdict.
        review_mode = await artifact_review_service.get_review_mode(db, run.project_id)
        created_ids = []
        for rv in data.get("reviews", []):
            script_id = None
            target_ref = rv.get("target_ref")
            for s in input_data.get("scripts", []):
                tc_id = s.get("test_case", {}).get("test_case_id")
                if (tc_id and tc_id == target_ref) or (not tc_id and str(s.get("script_id")) == target_ref):
                    script_id = s.get("script_id")
                    break
            if script_id is None:
                continue
            review = await artifact_review_service.create_review(
                db,
                project_id=run.project_id,
                agent_run_id=run.id,
                artifact_type="automation_script",
                artifact_id=script_id,
                reviewer_agent="automation_script_review",
                scores=rv.get("scores"),
                overall_score=rv.get("overall_score"),
                verdict=rv.get("verdict", "needs_revision"),
                findings=rv.get("findings"),
                coverage_gaps=rv.get("coverage_gaps"),
                review_mode=review_mode,
            )
            created_ids.append(review.id)
        return {"review_ids": created_ids, "count": len(created_ids), "summary": data.get("summary")}

    if agent_name == "test_execution":
        summary = data.get("summary", {})
        results = data.get("results", [])
        test_cases = input_data.get("test_cases", [])
        source_type = input_data.get("source_type", "manual")
        # Map source_type → execution_type. Post-migration 025, AI runs are a
        # mode of automation, not their own type — carried via metadata.ai_assisted.
        if source_type in ("ai", "automation", "automation_local", "external_automation_tool"):
            execution_type = "automation"
        else:
            execution_type = "manual"
        run_metadata: dict[str, Any] = {"source_type": source_type}
        if source_type == "ai":
            run_metadata["ai_assisted"] = True
        # The agent may surface an aggregate confidence score for AI runs.
        confidence_score = data.get("overall_confidence")
        if confidence_score is None and isinstance(data.get("summary"), dict):
            confidence_score = data["summary"].get("overall_confidence")
        run_record = ExecutionRun(
            project_id=run.project_id,
            created_by=run.triggered_by,
            execution_id=temporary_id("ER"),
            suite_name=input_data.get("suite_name", "Agent Test Suite"),
            environment=input_data.get("environment", "local"),
            status="completed",
            execution_type=execution_type,
            source_type=source_type,
            confidence_score=confidence_score,
            metadata_=run_metadata,
            total_tests=summary.get("total", len(results)),
            passed=summary.get("passed", 0),
            failed=summary.get("failed", 0),
            skipped=summary.get("skipped", 0),
            execution_logs=getattr(agent_result, "logs", []),
            agent_run_id=run.id,
        )
        db.add(run_record)
        await db.flush()
        run_record.execution_id = display_id("ER", run_record.id)
        await db.flush()
        await traceability_service.create_lineage_many(
            db,
            project_id=run.project_id,
            parents=[("test_case", tc.get("id")) for tc in test_cases if tc.get("id")],
            child_type="execution_run",
            child_id=run_record.id,
            agent_run_id=run.id,
        )
        tc_map = {tc.get("test_case_id"): tc.get("id") for tc in test_cases}
        result_ids = []
        now = datetime.now(timezone.utc)
        for result_data in results:
            db_tc_id = tc_map.get(result_data.get("test_case_id"))
            exec_result = ExecutionResult(
                execution_run_id=run_record.id,
                test_case_id=db_tc_id,
                project_id=run.project_id,
                test_name=result_data.get("test_name", "Unknown"),
                status=result_data.get("status", "passed"),
                duration_ms=result_data.get("duration_ms"),
                error_message=_to_text(result_data.get("error_message")),
                stack_trace=_to_text(result_data.get("stack_trace")),
                logs=_to_list(result_data.get("logs")),
                metadata_=result_data.get("metadata") if isinstance(result_data.get("metadata"), dict) else None,
            )
            db.add(exec_result)
            await db.flush()
            if db_tc_id:
                tc = await db.get(TestCase, db_tc_id)
                if tc:
                    tc.last_execution_run_id = run_record.id
                    tc.last_automation_status = exec_result.status
                    tc.last_automation_run_at = now
                    tc.latest_evidence_available = bool(exec_result.logs or exec_result.error_message or exec_result.stack_trace)
                    tc.last_status_updated_by = run.triggered_by
                    tc.last_status_updated_at = now
                await coverage_matrix_service.record_execution_status(
                    db, test_case_id=db_tc_id, execution_status=exec_result.status
                )
            parents = [("execution_run", run_record.id)]
            if db_tc_id:
                parents.append(("test_case", db_tc_id))
            await traceability_service.create_lineage_many(
                db,
                project_id=run.project_id,
                parents=parents,
                child_type="execution_result",
                child_id=exec_result.id,
                agent_run_id=run.id,
            )
            result_ids.append(exec_result.id)
        # AI-assisted runs still go through the autonomous/review completion rule.
        # Post-migration 025 execution_type is 'automation' for these; source_type
        # remains the source of truth for "this run is AI-assisted".
        if source_type == "ai":
            from app.services import ai_execution_service
            results_for_eval = list(
                (await db.execute(
                    select(ExecutionResult).where(ExecutionResult.execution_run_id == run_record.id)
                )).scalars().all()
            )
            evaluation = await ai_execution_service.finalize_ai_run(
                db, run=run_record, results=results_for_eval,
            )
            summary["ai_completion_decision"] = evaluation.decision
            summary["ai_completion_reason"] = evaluation.reason
        return {"run_id": run_record.id, "result_ids": result_ids, "summary": summary}

    if agent_name == "defect_analysis":
        failed = input_data.get("failed_results", [])
        er_map = {r.get("test_name"): r.get("id") for r in failed}
        tc_map = {r.get("test_name"): r.get("test_case_id") for r in failed}
        created = []
        for defect_data in data.get("defects", []):
            ref = defect_data.get("execution_result_ref", "")
            draft = DefectDraft(
                project_id=run.project_id,
                test_case_id=tc_map.get(ref),
                execution_result_id=er_map.get(ref),
                created_by=run.triggered_by,
                defect_id=temporary_id("DEF"),
                summary=defect_data.get("summary", "Defect detected"),
                description=defect_data.get("description"),
                steps_to_reproduce=defect_data.get("steps_to_reproduce"),
                expected_result=defect_data.get("expected_result"),
                actual_result=defect_data.get("actual_result"),
                severity=defect_data.get("severity", "Medium"),
                priority=defect_data.get("priority", "Medium"),
                root_cause_hypothesis=defect_data.get("root_cause_hypothesis"),
                classification=defect_data.get("classification", "product_defect"),
                status="draft",
                jira_ready=False,
                agent_run_id=run.id,
            )
            db.add(draft)
            await db.flush()
            draft.defect_id = display_id("DEF", draft.id)
            await db.flush()
            parents = []
            if er_map.get(ref):
                parents.append(("execution_result", er_map.get(ref)))
            if tc_map.get(ref):
                parents.append(("test_case", tc_map.get(ref)))
            await traceability_service.create_lineage_many(
                db,
                project_id=run.project_id,
                parents=parents,
                child_type="defect_draft",
                child_id=draft.id,
                agent_run_id=run.id,
            )
            if tc_map.get(ref):
                await coverage_matrix_service.record_defect_linked(
                    db, test_case_id=tc_map[ref], defect_id=draft.id
                )
            created.append(draft.id)
        return {"defect_ids": created, "count": len(created)}

    if agent_name == "test_reporting":
        report_data = data.get("report", {})
        report = Report(
            project_id=run.project_id,
            created_by=run.triggered_by,
            report_id=temporary_id("RPT"),
            report_type=input_data.get("report_type", "summary"),
            title=report_data.get("title", "Test Report"),
            summary=report_data.get("summary"),
            coverage=report_data.get("coverage"),
            execution_metrics=report_data.get("execution_metrics"),
            defect_metrics=report_data.get("defect_metrics"),
            risks=report_data.get("risks", []),
            recommendations=report_data.get("recommendations", []),
            status="draft",
            agent_run_id=run.id,
            metadata_={"raw_metrics": input_data.get("metrics")},
        )
        db.add(report)
        await db.flush()
        report.report_id = display_id("RPT", report.id)
        await db.flush()
        await traceability_service.create_lineage(
            db,
            project_id=run.project_id,
            parent_type="project",
            parent_id=run.project_id,
            child_type="report",
            child_id=report.id,
            agent_run_id=run.id,
        )
        return {"report_id": report.id, "report_ref": report.report_id}

    if agent_name == "test_classification":
        return await classification_service.persist_classification_result(db, run, input_data, data)

    return None


def classify_exception(exc: Exception) -> str:
    if isinstance(exc, PermanentAgentError):
        return "permanent"
    if isinstance(exc, TransientAgentError):
        return "transient"
    if isinstance(exc, (TimeoutError, ConnectionError, socket.timeout, httpx.TimeoutException, httpx.ConnectError)):
        return "transient"
    return "permanent"


async def _mark_agent_failed(agent_run_id: int, exc: Exception) -> None:
    async with AsyncSessionLocal() as db:
        await agent_run_service.fail_agent_run(db, agent_run_id, error_message=str(exc))
        await db.commit()


async def _run_agent_with_project_llm_routes(
    db,
    run: AgentRun,
    agent_name: str,
    agent_func: AgentCallable,
    input_data: dict[str, Any],
) -> Any:
    role = agent_role(agent_name)
    # Fetched once and shared with the vision lookup below — both are
    # in-memory filters over the same project settings rows, so this keeps
    # the DB round-trip count the same as before role routing existed.
    settings_rows = await list_settings(db, run.project_id)
    routes = await resolve_project_llm_routes(
        db,
        project_id=run.project_id,
        module_scope=input_data.get("module_scope") or get_agent_spec(agent_name).module_scope,
        role=role,
        rows=settings_rows,
    )

    # Pin the project's vision route for the whole run (not per fallback
    # attempt) so nested get_vision_llm() calls inside this agent — e.g. UI
    # screenshot analysis called from a reasoning/coding agent — resolve the
    # vision role correctly instead of collapsing onto whichever text route
    # is active in the loop below.
    vision_routes = await resolve_project_llm_routes(db, project_id=run.project_id, role="vision", rows=settings_rows)
    vision_top = vision_routes[0] if vision_routes else None
    vision_token = set_llm_role_route_overrides(
        {
            "vision": LLMRouteOverride(
                provider=vision_top.provider_key,
                model=vision_top.model_name,
                temperature=vision_top.temperature,
                max_tokens=vision_top.max_tokens,
                timeout_seconds=vision_top.timeout_seconds,
                role="vision",
            )
        }
        if vision_top is not None
        else {}
    )

    try:
        last_result: Any = None
        last_error: Exception | None = None
        for index, route in enumerate(routes):
            token = set_llm_route_override(
                LLMRouteOverride(
                    provider=route.provider_key,
                    model=route.model_name,
                    temperature=route.temperature,
                    max_tokens=route.max_tokens,
                    timeout_seconds=route.timeout_seconds,
                    role=role,
                )
            )
            try:
                await agent_run_service.add_log(
                    db,
                    run,
                    level="info",
                    step="llm_route",
                    message=f"Using LLM provider {route.provider_name} ({route.model_name}) from {route.source} for role {role}",
                )
                await db.commit()
                result = await agent_func(input_data or {})
                if _is_success(result):
                    return result
                last_result = result
                if index < len(routes) - 1:
                    await agent_run_service.add_log(
                        db,
                        run,
                        level="warning",
                        step="llm_fallback",
                        message=f"LLM provider {route.provider_name} failed; trying fallback provider",
                    )
                    await db.commit()
                    continue
                return result
            except Exception as exc:
                last_error = exc
                if index < len(routes) - 1:
                    await agent_run_service.add_log(
                        db,
                        run,
                        level="warning",
                        step="llm_fallback",
                        message=f"LLM provider {route.provider_name} errored; trying fallback provider",
                        data={"error_type": type(exc).__name__},
                    )
                    await db.commit()
                    continue
                raise
            finally:
                reset_llm_route_override(token)

        if last_error is not None:
            raise last_error
        return last_result
    finally:
        reset_llm_role_route_overrides(vision_token)


async def _run_agent_task(task_id: str, agent_run_id: int, agent_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"AgentRun {agent_run_id} not found")

        if run.status == "cancelled":
            # Cancelled while still queued — never overwrite a user's cancel.
            return {"agent_run_id": agent_run_id, "status": "cancelled"}

        # ── duplicate-delivery guard ──────────────────────────────────────
        # `task_acks_late=True` means a task is only acknowledged once it
        # finishes, so work survives a crashed worker — and a task killed
        # mid-flight is redelivered when a worker reconnects. That is the
        # behaviour we want, but nothing stopped the redelivered copy from
        # executing an agent run that had since been retried and completed.
        #
        # Observed live 2026-08-03: a task killed by a worker restart was
        # redelivered ~1h later, re-ran an agent run that had already
        # completed via the Studio retry button, produced a duplicate script
        # for TC-0079, and — because both ran against one local model —
        # roughly doubled the wall-clock time of an unrelated run happening
        # at the same time.
        if run.status in _TERMINAL_AGENT_STATUSES:
            logger.warning(
                "agent_tasks: refusing duplicate delivery of task %s for run %s — already %s",
                task_id, agent_run_id, run.status,
            )
            return {"agent_run_id": agent_run_id, "status": run.status, "skipped": "already_terminal"}

        # A newer dispatch owns this run. `enqueue_agent_run` writes its task
        # id when it requeues, so a delivery carrying an older id is a stale
        # copy of work that has been superseded — including the case where
        # the newer attempt is still running, which the status check above
        # cannot see.
        if run.celery_task_id and run.celery_task_id != task_id:
            logger.warning(
                "agent_tasks: refusing superseded delivery of task %s for run %s — owned by task %s",
                task_id, agent_run_id, run.celery_task_id,
            )
            return {"agent_run_id": agent_run_id, "status": run.status, "skipped": "superseded"}

        run.status = "running"
        run.celery_task_id = task_id
        await agent_run_service.update_progress(db, run, percent=10, message="Worker started", step="running")
        await db.commit()
        await db.refresh(run)

        try:
            agent_func = AGENT_REGISTRY[agent_name]
        except KeyError:
            message = f"Unsupported agent '{agent_name}'"
            await agent_run_service.fail_agent_run(db, run, error_message=message)
            await db.commit()
            return {"agent_run_id": agent_run_id, "status": "failed", "error": message}

        spec = get_agent_spec(agent_name)
        try:
            await agent_run_service.update_progress(db, run, percent=30, message="Agent execution started")
            await db.commit()

            # Let the agent narrate its own work between the two milestones
            # this wrapper owns. Committed on each report, because the UI reads
            # the row from a different session — a flush alone would leave the
            # spinner showing the same 30% it always showed.
            async def _report(percent: int, message: str) -> None:
                scaled = _AGENT_PROGRESS_FLOOR + int(
                    (_AGENT_PROGRESS_CEILING - _AGENT_PROGRESS_FLOOR) * percent / 100
                )
                await agent_run_service.update_progress(db, run, percent=scaled, message=message)
                await db.commit()

            progress_token = agent_progress.set_progress_reporter(_report)
            try:
                agent_result = await asyncio.wait_for(
                    _run_agent_with_project_llm_routes(
                        db,
                        run,
                        agent_name,
                        agent_func,
                        input_data or {},
                    ),
                    timeout=spec.timeout_seconds
                )
            except (asyncio.TimeoutError, TimeoutError):
                error = f"Agent execution timed out after {int(spec.timeout_seconds)} seconds."
                await agent_run_service.fail_agent_run(
                    db,
                    run,
                    error_message=error,
                )
                await db.commit()
                return {"agent_run_id": agent_run_id, "status": "failed", "error": error}
            finally:
                agent_progress.reset_progress_reporter(progress_token)

            # Re-check from the DB (not the in-memory `run`) — a concurrent
            # cancel request commits from a different session, so only a
            # fresh read observes it.
            cancel_check = await db.execute(select(AgentRun.status).where(AgentRun.id == agent_run_id))
            if cancel_check.scalar_one_or_none() == "cancelled":
                return {"agent_run_id": agent_run_id, "status": "cancelled"}

            if _is_success(agent_result):
                await agent_run_service.update_progress(db, run, percent=90, message="Persisting agent result")
                output_data = await _persist_agent_artifacts(db, run, agent_name, input_data or {}, agent_result)
                await agent_run_service.complete_agent_run(db, run, agent_result=agent_result, output_data=output_data)
                await db.commit()
                await _chain_next_agents(db, run, agent_name, input_data or {}, output_data)
                return {"agent_run_id": agent_run_id, "status": "completed"}

            error = getattr(agent_result, "error", None) or "Agent failed"
            await agent_run_service.fail_agent_run(
                db,
                run,
                error_message=error,
                agent_result=agent_result,
            )
            await db.commit()
            return {"agent_run_id": agent_run_id, "status": "failed", "error": error}
        except Exception as exc:
            logger.exception("Agent task failed: agent=%s run_id=%s", agent_name, agent_run_id)
            await db.rollback()
            raise


@celery_app.task(bind=True, name="agent_tasks.run_agent", max_retries=3, default_retry_delay=1)
def run_agent(self, agent_run_id: int, agent_name: str, input_data: dict[str, Any] | None = None):
    """Dispatch a registered agent and persist run status, output, and logs."""
    logger.info("Agent task started: agent=%s run_id=%s", agent_name, agent_run_id)
    try:
        return asyncio.run(_run_agent_task(self.request.id, agent_run_id, agent_name, input_data or {}))
    except Exception as exc:
        if classify_exception(exc) == "transient" and self.request.retries < self.max_retries:
            countdown = min(2 ** self.request.retries, 30)
            raise self.retry(exc=exc, countdown=countdown)
        asyncio.run(_mark_agent_failed(agent_run_id, exc))
        raise
