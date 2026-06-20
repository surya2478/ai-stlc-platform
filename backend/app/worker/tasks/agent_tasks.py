"""Celery tasks for dispatching AI agent runs asynchronously."""
from __future__ import annotations

import asyncio
import logging
import socket
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from sqlalchemy import select

from app.agents.automation.automation_agent import AutomationScriptAgent
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
from app.agents.test_planning.test_case_agent import TestCaseDevelopmentAgent
from app.database import AsyncSessionLocal
from app.models.agent import AgentRun
from app.models.automation_script import AutomationScript
from app.models.defect import DefectDraft
from app.models.document import UploadedDocument
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.report import Report
from app.models.requirement import Requirement
from app.models.requirement_review import RequirementQualityReview
from app.models.test_case import TestCase
from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.llm.provider import LLMRouteOverride, reset_llm_route_override, set_llm_route_override
from app.services import agent_run_service
from app.services import requirement_service
from app.services.display_id_service import display_id, temporary_id
from app.services.project_llm_settings_service import resolve_project_llm_routes
from app.services import traceability_service
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)

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


async def _ui_image_analysis(input_data: dict[str, Any]) -> Any:
    return await UIAnalysisAgent().run(
        image_path=input_data["image_path"],
        image_name=input_data.get("image_name", "screenshot"),
        context_note=input_data.get("context_note", ""),
        project_id=input_data.get("project_id", 0),
    )


async def _url_analysis(input_data: dict[str, Any]) -> Any:
    return await URLAnalysisAgent().run(
        url=input_data["url"],
        crawl_depth=input_data.get("crawl_depth", 0),
        context_note=input_data.get("context_note", ""),
        project_id=input_data.get("project_id", 0),
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


async def _test_case(input_data: dict[str, Any]) -> Any:
    return await TestCaseDevelopmentAgent().run(scenarios=input_data["scenarios"])


async def _automation_script(input_data: dict[str, Any]) -> Any:
    return await AutomationScriptAgent().run(
        test_cases=input_data["test_cases"],
        framework=input_data.get("framework", "playwright"),
    )


async def _test_execution(input_data: dict[str, Any]) -> Any:
    return await TestExecutionAgent().run(
        test_cases=input_data["test_cases"],
        environment=input_data.get("environment", "local"),
        suite_name=input_data.get("suite_name", "Agent Test Suite"),
    )


async def _defect_analysis(input_data: dict[str, Any]) -> Any:
    return await DefectAnalysisAgent().run(
        failed_results=input_data["failed_results"],
        project_name=input_data.get("project_name", "Project"),
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
    "test_case": _test_case,
    "automation_script": _automation_script,
    "test_execution": _test_execution,
    "defect_analysis": _defect_analysis,
    "test_reporting": _test_reporting,
}


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
                source_document_id=document_id,
                status="pending_review",
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
                status="pending_review",
                readiness_status="ai_review_pending",
                metadata_={
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
                    status="pending_review",
                    readiness_status="ai_review_pending",
                    metadata_={
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
                status="pending_review",
                readiness_status="ai_review_pending",
                metadata_={
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

    if agent_name == "test_case":
        scenarios = input_data.get("scenarios", [])
        scenario_id_map = {s.get("scenario_id"): s.get("id") for s in scenarios}
        req_id_map = {s.get("id"): s.get("_source_requirement_id") for s in scenarios}
        created = []
        for tc_data in data.get("test_cases", []):
            db_sc_id = scenario_id_map.get(tc_data.get("_source_scenario_id"))
            db_req_id = req_id_map.get(db_sc_id)
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
                status="draft",
                agent_run_id=run.id,
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

    if agent_name == "automation_script":
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
                status="draft",
                agent_run_id=run.id,
            )
            db.add(script)
            await db.flush()
            script.script_id = display_id("AS", script.id)
            await db.flush()
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
            created.append(script.id)
        return {"script_ids": created, "count": len(created)}

    if agent_name == "test_execution":
        summary = data.get("summary", {})
        results = data.get("results", [])
        test_cases = input_data.get("test_cases", [])
        run_record = ExecutionRun(
            project_id=run.project_id,
            created_by=run.triggered_by,
            execution_id=temporary_id("ER"),
            suite_name=input_data.get("suite_name", "Agent Test Suite"),
            environment=input_data.get("environment", "local"),
            status="completed",
            source_type=input_data.get("source_type", "manual"),
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
            )
            db.add(exec_result)
            await db.flush()
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
    routes = await resolve_project_llm_routes(
        db,
        project_id=run.project_id,
        module_scope=input_data.get("module_scope"),
    )
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
            )
        )
        try:
            await agent_run_service.add_log(
                db,
                run,
                level="info",
                step="llm_route",
                message=f"Using LLM provider {route.provider_name} ({route.model_name}) from {route.source}",
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


async def _run_agent_task(task_id: str, agent_run_id: int, agent_name: str, input_data: dict[str, Any]) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(AgentRun).where(AgentRun.id == agent_run_id))
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"AgentRun {agent_run_id} not found")

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

        try:
            await agent_run_service.update_progress(db, run, percent=30, message="Agent execution started")
            await db.commit()
            try:
                agent_result = await asyncio.wait_for(
                    _run_agent_with_project_llm_routes(
                        db,
                        run,
                        agent_name,
                        agent_func,
                        input_data or {},
                    ),
                    timeout=120.0
                )
            except (asyncio.TimeoutError, TimeoutError):
                error = "Agent execution timed out after 120 seconds."
                await agent_run_service.fail_agent_run(
                    db,
                    run,
                    error_message=error,
                )
                await db.commit()
                return {"agent_run_id": agent_run_id, "status": "failed", "error": error}

            if _is_success(agent_result):
                await agent_run_service.update_progress(db, run, percent=90, message="Persisting agent result")
                output_data = await _persist_agent_artifacts(db, run, agent_name, input_data or {}, agent_result)
                await agent_run_service.complete_agent_run(db, run, agent_result=agent_result, output_data=output_data)
                await db.commit()
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
