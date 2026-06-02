"""
Test Plans, Scenarios, and Test Cases endpoints.
"""
import json
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select, func

from app.api.deps import DBSession, OptionalUser
from app.models.requirement import Requirement
from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase
from app.models.project import Project
from app.schemas.test_plan import (
    TestPlanOut, TestPlanUpdate,
    TestScenarioOut,
    TestCaseOut, TestCaseUpdate,
    AgentPlanTrigger, AgentCaseTrigger,
)
from app.schemas.requirement import ApprovalRequest
from app.services import test_plan_service
from app.agents.test_planning.planning_agent import TestPlanningAgent
from app.agents.test_planning.scenario_agent import TestScenarioAgent
from app.agents.test_planning.test_case_agent import TestCaseDevelopmentAgent

router = APIRouter()


# ── Test Plans ────────────────────────────────────────────────────────────────

@router.get("/project/{project_id}", response_model=list[TestPlanOut])
async def list_test_plans(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    return await test_plan_service.list_test_plans(db, project_id)


@router.get("/{plan_id}", response_model=TestPlanOut)
async def get_test_plan(
    plan_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    plan = await test_plan_service.get_test_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")
    return plan


@router.patch("/{plan_id}", response_model=TestPlanOut)
async def update_test_plan(
    plan_id: int,
    updates: TestPlanUpdate,
    db: DBSession,
    current_user: OptionalUser,
):
    plan = await test_plan_service.get_test_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")
    plan = await test_plan_service.update_test_plan(db, plan, updates)
    await db.commit()
    return plan


@router.post("/{plan_id}/approve", response_model=TestPlanOut)
async def approve_test_plan(
    plan_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    plan = await test_plan_service.get_test_plan(db, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Test plan not found")
    plan = await test_plan_service.approve_test_plan(db, plan, body.action, body.notes)
    await db.commit()
    return plan


# ── Scenarios ─────────────────────────────────────────────────────────────────

@router.get("/scenarios/project/{project_id}", response_model=list[TestScenarioOut])
async def list_scenarios(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    requirement_id: int | None = Query(None),
):
    return await test_plan_service.list_scenarios(db, project_id, requirement_id)


@router.get("/scenarios/{scenario_id}", response_model=TestScenarioOut)
async def get_scenario(
    scenario_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    sc = await test_plan_service.get_scenario(db, scenario_id)
    if not sc:
        raise HTTPException(status_code=404, detail="Scenario not found")
    return sc


# ── Test Cases ────────────────────────────────────────────────────────────────

@router.get("/cases/project/{project_id}", response_model=list[TestCaseOut])
async def list_test_cases(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    scenario_id: int | None = Query(None),
    requirement_id: int | None = Query(None),
    status: str | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    return await test_plan_service.list_test_cases(
        db, project_id, scenario_id, requirement_id, status, skip, limit
    )


@router.get("/cases/{tc_id}", response_model=TestCaseOut)
async def get_test_case(
    tc_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    return tc


@router.patch("/cases/{tc_id}", response_model=TestCaseOut)
async def update_test_case(
    tc_id: int,
    updates: TestCaseUpdate,
    db: DBSession,
    current_user: OptionalUser,
):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    tc = await test_plan_service.update_test_case(db, tc, updates)
    await db.commit()
    return tc


@router.post("/cases/{tc_id}/approve", response_model=TestCaseOut)
async def approve_test_case(
    tc_id: int,
    body: ApprovalRequest,
    db: DBSession,
    current_user: OptionalUser,
):
    tc = await test_plan_service.get_test_case(db, tc_id)
    if not tc:
        raise HTTPException(status_code=404, detail="Test case not found")
    tc = await test_plan_service.approve_test_case(db, tc, body.action, body.notes)
    await db.commit()
    return tc


# ── Agent Endpoints ───────────────────────────────────────────────────────────

@router.post("/agent/generate-plan")
async def trigger_planning_agent(
    body: AgentPlanTrigger,
    db: DBSession,
    current_user: OptionalUser,
):
    """
    Trigger Agent 3 (Test Planning) from approved requirements.
    Creates a structured test plan record.
    """
    # Load project name
    result = await db.execute(select(Project).where(Project.id == body.project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Load requirements — only approved ones are allowed
    reqs = []
    not_approved = []
    wrong_project = []
    for rid in body.requirement_ids:
        result = await db.execute(select(Requirement).where(Requirement.id == rid))
        r = result.scalar_one_or_none()
        if not r:
            continue
        if r.project_id != body.project_id:
            wrong_project.append(rid)
            continue
        if r.status != "approved":
            not_approved.append(rid)
            continue
        reqs.append({
            "id": r.id,
            "requirement_id": r.requirement_id,
            "title": r.title,
            "summary": r.summary,
            "acceptance_criteria": r.acceptance_criteria,
            "business_rules": r.business_rules,
            "risks": r.risks,
        })

    if wrong_project:
        raise HTTPException(
            status_code=403,
            detail=f"Requirement ID(s) {wrong_project} do not belong to project {body.project_id}",
        )
    if not reqs:
        if not_approved:
            raise HTTPException(
                status_code=422,
                detail=f"Only approved requirements can be used for test planning. "
                       f"Not yet approved: {not_approved}",
            )
        raise HTTPException(status_code=422, detail="No valid requirements found")

    agent = TestPlanningAgent()
    agent_result = await agent.run(requirements=reqs, project_name=project.name)

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    plan_data = agent_result.data["test_plan"]

    # Count existing plans for ID generation
    count_result = await db.execute(
        select(func.count()).where(TestPlan.project_id == body.project_id)
    )
    plan_count = count_result.scalar_one()
    plan_id_str = f"TP-{(plan_count + 1):04d}"

    plan = TestPlan(
        project_id=body.project_id,
        created_by=(current_user.id if current_user else 1),
        test_plan_id=plan_id_str,
        title=plan_data.get("title", f"Test Plan — {project.name}"),
        scope=plan_data.get("scope"),
        out_of_scope=plan_data.get("out_of_scope"),
        test_types=plan_data.get("test_types"),
        entry_criteria=plan_data.get("entry_criteria"),
        exit_criteria=plan_data.get("exit_criteria"),
        risks=plan_data.get("risks"),
        mitigations=plan_data.get("mitigations"),
        automation_candidates=plan_data.get("automation_candidates"),
        estimated_effort=(
            plan_data["estimated_effort"]
            if isinstance(plan_data.get("estimated_effort"), str)
            else json.dumps(plan_data["estimated_effort"])
            if plan_data.get("estimated_effort") is not None
            else None
        ),
        resource_recommendation=(
            plan_data["resource_recommendation"]
            if isinstance(plan_data.get("resource_recommendation"), str)
            else json.dumps(plan_data["resource_recommendation"])
            if plan_data.get("resource_recommendation") is not None
            else None
        ),
        status="draft",
        metadata_={"source_requirement_ids": body.requirement_ids},
    )
    db.add(plan)
    await db.flush()
    await db.refresh(plan)
    await db.commit()

    return {
        "message": "Test plan generated successfully",
        "plan_id": plan.id,
        "test_plan_id": plan.test_plan_id,
        "agent_logs": agent_result.logs,
    }


@router.post("/agent/generate-scenarios")
async def trigger_scenario_agent(
    body: AgentPlanTrigger,
    db: DBSession,
    current_user: OptionalUser,
):
    """
    Trigger Agent 4 (Test Scenario) from requirements.
    Creates TestScenario records.
    """
    reqs = []
    for rid in body.requirement_ids:
        result = await db.execute(select(Requirement).where(Requirement.id == rid))
        r = result.scalar_one_or_none()
        if r:
            reqs.append({
                "id": r.id,
                "requirement_id": r.requirement_id,
                "title": r.title,
                "summary": r.summary,
                "acceptance_criteria": r.acceptance_criteria,
                "business_rules": r.business_rules,
                "user_roles": r.user_roles,
            })

    if not reqs:
        raise HTTPException(status_code=422, detail="No valid requirements found")

    agent = TestScenarioAgent()
    agent_result = await agent.run(requirements=reqs)

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    # Count existing scenarios for unique IDs
    count_result = await db.execute(
        select(func.count()).where(TestScenario.project_id == body.project_id)
    )
    sc_count = count_result.scalar_one()

    created_ids = []
    for i, sc_data in enumerate(agent_result.data.get("scenarios", [])):
        # Map back to DB requirement_id
        src_req_id = sc_data.get("_source_requirement_id")
        db_req_id = None
        if src_req_id:
            for r in reqs:
                if r["id"] == src_req_id or r["requirement_id"] == src_req_id:
                    db_req_id = r["id"]
                    break

        sc = TestScenario(
            project_id=body.project_id,
            requirement_id=db_req_id,
            created_by=(current_user.id if current_user else 1),
            scenario_id=f"TS-{(sc_count + i + 1):04d}",
            title=sc_data.get("title", "Untitled Scenario"),
            description=sc_data.get("description"),
            scenario_type=sc_data.get("scenario_type", "positive"),
            priority=sc_data.get("priority", "Medium"),
            coverage_mapping=sc_data.get("coverage_mapping"),
            status="draft",
        )
        db.add(sc)
        await db.flush()
        created_ids.append(sc.id)

    await db.commit()
    return {
        "message": f"Generated {len(created_ids)} test scenarios",
        "scenario_ids": created_ids,
        "agent_logs": agent_result.logs,
    }


@router.post("/agent/generate-cases")
async def trigger_test_case_agent(
    body: AgentCaseTrigger,
    db: DBSession,
    current_user: OptionalUser,
):
    """
    Trigger Agent 5 (Test Case Development) from test scenarios.
    Creates detailed TestCase records.
    """
    scenarios = []
    if body.scenario_ids:
        for sid in body.scenario_ids:
            result = await db.execute(select(TestScenario).where(TestScenario.id == sid))
            s = result.scalar_one_or_none()
            if s:
                scenarios.append({
                    "id": s.id,
                    "scenario_id": s.scenario_id,
                    "title": s.title,
                    "description": s.description,
                    "scenario_type": s.scenario_type,
                    "priority": s.priority,
                    "coverage_mapping": s.coverage_mapping,
                    "_source_requirement_id": s.requirement_id,
                })
    elif body.requirement_ids:
        for rid in body.requirement_ids:
            result = await db.execute(
                select(TestScenario).where(TestScenario.requirement_id == rid)
            )
            for s in result.scalars().all():
                scenarios.append({
                    "id": s.id,
                    "scenario_id": s.scenario_id,
                    "title": s.title,
                    "description": s.description,
                    "scenario_type": s.scenario_type,
                    "priority": s.priority,
                    "coverage_mapping": s.coverage_mapping,
                    "_source_requirement_id": s.requirement_id,
                })

    # Fallback: if requirement-based lookup yielded nothing, use all project scenarios
    if not scenarios and body.requirement_ids:
        result = await db.execute(
            select(TestScenario).where(TestScenario.project_id == body.project_id)
        )
        for s in result.scalars().all():
            scenarios.append({
                "id": s.id,
                "scenario_id": s.scenario_id,
                "title": s.title,
                "description": s.description,
                "scenario_type": s.scenario_type,
                "priority": s.priority,
                "coverage_mapping": s.coverage_mapping,
                "_source_requirement_id": s.requirement_id,
            })

    if not scenarios:
        raise HTTPException(status_code=422, detail="No scenarios found to generate test cases from")

    agent = TestCaseDevelopmentAgent()
    agent_result = await agent.run(scenarios=scenarios)

    if not agent_result.success:
        raise HTTPException(status_code=500, detail=agent_result.error or "Agent failed")

    # Count existing test cases for IDs
    count_result = await db.execute(
        select(func.count()).where(TestCase.project_id == body.project_id)
    )
    tc_count = count_result.scalar_one()

    # Build scenario ID → DB id map
    scenario_id_map = {s["scenario_id"]: s["id"] for s in scenarios}
    req_id_map = {s["id"]: s["_source_requirement_id"] for s in scenarios}

    created_ids = []
    for i, tc_data in enumerate(agent_result.data.get("test_cases", [])):
        src_sc_id = tc_data.get("_source_scenario_id")
        db_sc_id = scenario_id_map.get(src_sc_id) if src_sc_id else None
        db_req_id = req_id_map.get(db_sc_id) if db_sc_id else None

        tc = TestCase(
            project_id=body.project_id,
            scenario_id=db_sc_id,
            requirement_id=db_req_id,
            created_by=(current_user.id if current_user else 1),
            test_case_id=f"TC-{(tc_count + i + 1):04d}",
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
            tags=tc_data.get("tags"),
            status="draft",
        )
        db.add(tc)
        await db.flush()
        created_ids.append(tc.id)

    await db.commit()
    return {
        "message": f"Generated {len(created_ids)} test cases",
        "test_case_ids": created_ids,
        "agent_logs": agent_result.logs,
    }
