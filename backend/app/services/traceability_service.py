from __future__ import annotations

from math import ceil
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction
from app.models.artifact_lineage import ArtifactLineage
from app.models.automation_script import AutomationScript
from app.models.defect import DefectDraft
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.report import Report
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_data import TestData
from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.models.user import User
from app.schemas.traceability import (
    ApprovalDecisionRequest,
    CoverageGapsOut,
    LineageChainOut,
    LineageNode,
    TraceabilityChainItem,
    TraceabilityMatrixOut,
    TraceabilityMatrixRow,
)

ARTIFACT_MODELS: dict[str, type] = {
    "requirement": Requirement,
    "test_plan": TestPlan,
    "test_scenario": TestScenario,
    "test_case": TestCase,
    "test_data": TestData,
    "automation_script": AutomationScript,
    "execution_run": ExecutionRun,
    "execution_result": ExecutionResult,
    "defect_draft": DefectDraft,
    "report": Report,
}

APPROVAL_PERMISSIONS: dict[str, str] = {
    "requirement": "approve_requirements",
    "test_plan": "approve_test_plans",
    "test_scenario": "approve_test_plans",
    "test_case": "approve_test_cases",
    "test_data": "approve_test_data",
    "automation_script": "generate_automation",
    "execution_run": "execute_tests",
    "execution_result": "execute_tests",
    "defect_draft": "push_defects_to_jira",
    "report": "approve_release_report",
}

LIFECYCLE_STATUS_ARTIFACTS = {"execution_run", "execution_result"}


async def create_lineage(
    db: AsyncSession,
    *,
    project_id: int,
    parent_type: str,
    parent_id: int,
    child_type: str,
    child_id: int,
    agent_run_id: int | None = None,
    relationship_type: str = "generated_from",
    source: str = "agent",
    correlation_id: str | None = None,
    notes: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ArtifactLineage:
    lineage = ArtifactLineage(
        project_id=project_id,
        parent_type=parent_type,
        parent_id=parent_id,
        child_type=child_type,
        child_id=child_id,
        agent_run_id=agent_run_id,
        relationship_type=relationship_type,
        source=source,
        correlation_id=correlation_id,
        notes=notes,
        metadata_=metadata,
    )
    db.add(lineage)
    await db.flush()
    return lineage


async def create_lineage_many(
    db: AsyncSession,
    *,
    project_id: int,
    parents: list[tuple[str, int]],
    child_type: str,
    child_id: int,
    agent_run_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[ArtifactLineage]:
    entries = []
    for parent_type, parent_id in parents:
        entries.append(
            await create_lineage(
                db,
                project_id=project_id,
                parent_type=parent_type,
                parent_id=parent_id,
                child_type=child_type,
                child_id=child_id,
                agent_run_id=agent_run_id,
                metadata=metadata,
            )
        )
    return entries


# Preferred order of the STLC pipeline, used to sort lineage chains for display.
_LINEAGE_ORDER = [
    "requirement", "test_plan", "test_scenario", "test_case", "test_data",
    "automation_script", "execution_run", "execution_result", "defect_draft", "report",
]

_REF_ATTR_CANDIDATES = (
    "requirement_id", "test_case_id", "scenario_id", "plan_id", "script_id",
    "execution_id", "defect_id", "data_id", "report_id",
)
_TITLE_ATTR_CANDIDATES = ("title", "summary", "name", "suite_name", "test_name", "file_path")

_MAX_LINEAGE_DEPTH = 6


async def _hydrate_lineage_node(
    db: AsyncSession, entity_type: str, entity_id: int, relationship_type: str | None, depth: int
) -> LineageNode:
    """Resolve the display ref/title/status for a lineage node; tolerate deleted rows."""
    node = LineageNode(entity_type=entity_type, entity_id=entity_id, relationship_type=relationship_type, depth=depth)
    model = ARTIFACT_MODELS.get(entity_type)
    if model is None:
        return node
    result = await db.execute(select(model).where(model.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        node.title = "(deleted)"
        return node
    for attr in _REF_ATTR_CANDIDATES:
        value = getattr(entity, attr, None)
        if isinstance(value, str) and value:
            node.ref = value
            break
    for attr in _TITLE_ATTR_CANDIDATES:
        value = getattr(entity, attr, None)
        if isinstance(value, str) and value:
            node.title = value
            break
    node.status = getattr(entity, "status", None)
    return node


async def get_lineage_chain(
    db: AsyncSession, *, project_id: int, entity_type: str, entity_id: int
) -> LineageChainOut:
    """Walk artifact_lineage in both directions from one entity.

    Bounded breadth-first walk (depth ≤ _MAX_LINEAGE_DEPTH) with a visited-set
    cycle guard. Missing lineage rows are normal for artifacts created before
    lineage writes existed — the result is simply empty lists, never an error.
    """

    async def walk(direction: str) -> list[LineageNode]:
        nodes: list[LineageNode] = []
        visited: set[tuple[str, int]] = {(entity_type, entity_id)}
        frontier = [(entity_type, entity_id)]
        for depth in range(1, _MAX_LINEAGE_DEPTH + 1):
            if not frontier:
                break
            next_frontier: list[tuple[str, int]] = []
            for node_type, node_id in frontier:
                if direction == "upstream":
                    stmt = select(ArtifactLineage).where(
                        ArtifactLineage.project_id == project_id,
                        ArtifactLineage.child_type == node_type,
                        ArtifactLineage.child_id == node_id,
                    )
                else:
                    stmt = select(ArtifactLineage).where(
                        ArtifactLineage.project_id == project_id,
                        ArtifactLineage.parent_type == node_type,
                        ArtifactLineage.parent_id == node_id,
                    )
                for edge in (await db.execute(stmt)).scalars().all():
                    if direction == "upstream":
                        key = (edge.parent_type, edge.parent_id)
                    else:
                        key = (edge.child_type, edge.child_id)
                    if key in visited:
                        continue
                    visited.add(key)
                    next_frontier.append(key)
                    nodes.append(
                        await _hydrate_lineage_node(db, key[0], key[1], edge.relationship_type, depth)
                    )
            frontier = next_frontier

        def order_key(n: LineageNode) -> tuple[int, int]:
            try:
                pipeline_pos = _LINEAGE_ORDER.index(n.entity_type)
            except ValueError:
                pipeline_pos = len(_LINEAGE_ORDER)
            return (pipeline_pos, n.entity_id)

        return sorted(nodes, key=order_key)

    return LineageChainOut(
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        upstream=await walk("upstream"),
        downstream=await walk("downstream"),
    )


async def get_project_entity(db: AsyncSession, entity_type: str, entity_id: int):
    model = ARTIFACT_MODELS.get(entity_type)
    if model is None:
        raise HTTPException(status_code=404, detail="Unsupported artifact type")
    result = await db.execute(select(model).where(model.id == entity_id))
    entity = result.scalar_one_or_none()
    if entity is None:
        raise HTTPException(status_code=404, detail="Artifact not found")
    return entity


async def approve_artifact(
    db: AsyncSession,
    *,
    entity,
    entity_type: str,
    user: User,
    body: ApprovalDecisionRequest,
    request_id: str | None = None,
) -> ApprovalAction:
    old_status = getattr(entity, "status", None)
    decision = "approved" if body.action == "approve" else "rejected" if body.action == "reject" else "requested_changes"
    new_status = "approved" if decision == "approved" else "rejected" if decision == "rejected" else "pending_approval"
    old_metadata = dict(getattr(entity, "metadata_", None) or {})
    if entity_type in LIFECYCLE_STATUS_ARTIFACTS:
        entity.metadata_ = {
            **old_metadata,
            "approval_status": new_status,
            "approval_decision": decision,
        }
    elif hasattr(entity, "status"):
        entity.status = new_status
    action = ApprovalAction(
        project_id=entity.project_id,
        user_id=user.id,
        action_type=f"{body.action}_{entity_type}",
        entity_type=entity_type,
        entity_id=entity.id,
        decision=decision,
        notes=body.notes,
        changes_requested=body.changes_requested,
        source="platform",
        actor_role=user.role,
        old_value={
            "status": old_status,
            "approval_status": old_metadata.get("approval_status"),
        },
        new_value={
            "status": getattr(entity, "status", old_status),
            "approval_status": new_status,
        },
        jira_issue_key=getattr(entity, "jira_issue_key", None),
        correlation_id=body.correlation_id,
        request_id=request_id,
        agent_run_id=getattr(entity, "agent_run_id", None),
    )
    db.add(action)
    await db.flush()
    await db.refresh(action)
    return action


async def approval_history(
    db: AsyncSession,
    *,
    project_id: int,
    entity_type: str | None = None,
    entity_id: int | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[ApprovalAction], int]:
    stmt = select(ApprovalAction).where(ApprovalAction.project_id == project_id)
    count_stmt = select(func.count()).select_from(ApprovalAction).where(ApprovalAction.project_id == project_id)
    if entity_type:
        stmt = stmt.where(ApprovalAction.entity_type == entity_type)
        count_stmt = count_stmt.where(ApprovalAction.entity_type == entity_type)
    if entity_id is not None:
        stmt = stmt.where(ApprovalAction.entity_id == entity_id)
        count_stmt = count_stmt.where(ApprovalAction.entity_id == entity_id)
    stmt = stmt.order_by(ApprovalAction.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    total = (await db.execute(count_stmt)).scalar_one()
    return list((await db.execute(stmt)).scalars().all()), int(total)


async def traceability_matrix(
    db: AsyncSession,
    *,
    project_id: int,
    page: int,
    page_size: int,
    domain: str | None = None,
    phase: str | None = None,
    release: str | None = None,
    include_drafts: bool = False,
) -> TraceabilityMatrixOut:
    stmt = select(Requirement).where(Requirement.project_id == project_id)
    if not include_drafts:
        stmt = stmt.where(Requirement.status == "approved")
    stmt = stmt.order_by(Requirement.created_at.desc())
    requirements = list((await db.execute(stmt)).scalars().all())
    requirements = [_matches_filters(req, domain, phase, release) for req in requirements]
    requirements = [req for req in requirements if req is not None]
    total = len(requirements)
    page_items = requirements[(page - 1) * page_size: page * page_size]

    rows = []
    for req in page_items:
        test_cases = await _test_cases_for_requirement(db, req.id, include_drafts)
        tc_ids = [tc.id for tc in test_cases]
        results = await _execution_results_for_test_cases(db, project_id, tc_ids, include_drafts)
        defects = await _defects_for_results(db, project_id, [r.id for r in results], include_drafts)
        gaps = _row_gaps(test_cases, results, defects)
        rows.append(
            TraceabilityMatrixRow(
                requirement=_item(req, "requirement_id", "title"),
                test_cases=[_item(tc, "test_case_id", "title") for tc in test_cases],
                execution_results=[_result_item(result) for result in results],
                defects=[_item(defect, "defect_id", "summary") for defect in defects],
                gaps=gaps,
            )
        )
    return TraceabilityMatrixOut(
        items=rows,
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
        include_drafts=include_drafts,
    )


async def coverage_gaps(
    db: AsyncSession,
    *,
    project_id: int,
    include_drafts: bool = False,
) -> CoverageGapsOut:
    no_test_cases: list[int] = []
    no_execution: list[int] = []
    undecided_failures: list[int] = []
    page = 1
    while True:
        matrix = await traceability_matrix(
            db,
            project_id=project_id,
            page=page,
            page_size=200,
            include_drafts=include_drafts,
        )
        no_test_cases.extend(row.requirement.id for row in matrix.items if "no_test_cases" in row.gaps)
        no_execution.extend(row.requirement.id for row in matrix.items if "no_execution" in row.gaps)
        undecided_failures.extend(
            result.id
            for row in matrix.items
            for result in row.execution_results
            if "undecided_failures" in row.gaps
        )
        if page >= matrix.pages or not matrix.items:
            break
        page += 1
    return CoverageGapsOut(
        project_id=project_id,
        include_drafts=include_drafts,
        no_test_cases=no_test_cases,
        no_execution=no_execution,
        undecided_failures=undecided_failures,
    )


async def reporting_metrics(db: AsyncSession, project_id: int, *, include_drafts: bool = False) -> dict[str, Any]:
    approved = [] if include_drafts else [Requirement.status == "approved"]
    total_reqs = await _count(db, Requirement, project_id, *approved)
    total_tcs = await _count(db, TestCase, project_id, *( [] if include_drafts else [TestCase.status == "approved"] ))
    total_runs = await _count(db, ExecutionRun, project_id, *( [] if include_drafts else [_approved_execution_run_filter()] ))
    total_defects = await _count(db, DefectDraft, project_id, *( [] if include_drafts else [DefectDraft.status.in_(["approved", "pushed_to_jira"])] ))
    return {
        "requirements": {"total": total_reqs},
        "test_cases": {"total": total_tcs},
        "execution": {"total_runs": total_runs},
        "defects": {"total": total_defects},
        "include_drafts": include_drafts,
    }


async def _count(db: AsyncSession, model, project_id: int, *filters) -> int:
    stmt = select(func.count()).select_from(model).where(model.project_id == project_id)
    if filters:
        stmt = stmt.where(*filters)
    return int((await db.execute(stmt)).scalar_one())


def _json_approval_status_filter(model):
    return model.metadata_["approval_status"].astext == "approved"


def _approved_execution_run_filter():
    return or_(ExecutionRun.status == "approved", _json_approval_status_filter(ExecutionRun))


async def _test_cases_for_requirement(db: AsyncSession, requirement_id: int, include_drafts: bool) -> list[TestCase]:
    stmt = select(TestCase).where(TestCase.requirement_id == requirement_id)
    if not include_drafts:
        stmt = stmt.where(TestCase.status == "approved")
    return list((await db.execute(stmt)).scalars().all())


async def _execution_results_for_test_cases(db: AsyncSession, project_id: int, test_case_ids: list[int], include_drafts: bool) -> list[ExecutionResult]:
    if not test_case_ids:
        return []
    stmt = select(ExecutionResult).where(ExecutionResult.project_id == project_id, ExecutionResult.test_case_id.in_(test_case_ids))
    if not include_drafts:
        stmt = stmt.join(ExecutionRun, ExecutionRun.id == ExecutionResult.execution_run_id).where(_approved_execution_run_filter())
    return list((await db.execute(stmt)).scalars().all())


async def _defects_for_results(db: AsyncSession, project_id: int, result_ids: list[int], include_drafts: bool) -> list[DefectDraft]:
    if not result_ids:
        return []
    stmt = select(DefectDraft).where(DefectDraft.project_id == project_id, DefectDraft.execution_result_id.in_(result_ids))
    if not include_drafts:
        stmt = stmt.where(DefectDraft.status.in_(["approved", "pushed_to_jira"]))
    return list((await db.execute(stmt)).scalars().all())


def _row_gaps(test_cases: list[TestCase], results: list[ExecutionResult], defects: list[DefectDraft]) -> list[str]:
    gaps = []
    if not test_cases:
        gaps.append("no_test_cases")
    if test_cases and not results:
        gaps.append("no_execution")
    failed = [result for result in results if result.status in {"failed", "error"}]
    defect_result_ids = {defect.execution_result_id for defect in defects}
    if any(result.id not in defect_result_ids for result in failed):
        gaps.append("undecided_failures")
    return gaps


def _item(obj, ref_attr: str, title_attr: str) -> TraceabilityChainItem:
    return TraceabilityChainItem(
        id=obj.id,
        ref=getattr(obj, ref_attr, None),
        title=getattr(obj, title_attr, None) or getattr(obj, ref_attr, None) or str(obj.id),
        status=getattr(obj, "status", None),
    )


def _result_item(result: ExecutionResult) -> TraceabilityChainItem:
    return TraceabilityChainItem(id=result.id, ref=str(result.id), title=result.test_name, status=result.status)


def _matches_filters(req: Requirement, domain: str | None, phase: str | None, release: str | None) -> Requirement | None:
    metadata = req.metadata_ or {}
    checks = {
        "telecom_domain": domain,
        "test_phase": phase,
        "release_version": release,
    }
    for key, expected in checks.items():
        if expected is None:
            continue
        actual = getattr(req, key, None) or metadata.get(key)
        if actual != expected:
            return None
    return req
