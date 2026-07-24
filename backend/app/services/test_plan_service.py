"""
Test Plan, Test Scenario, and Test Case service — CRUD operations.
"""
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.orm import selectinload

from app.models.automation_mapping import AutomationTestMapping
from app.models.execution import ExecutionResult
from app.models.jira_connection import JiraConnection
from app.models.jira_sync import JiraSyncHistory
from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase, TestCaseHistory
from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.models.test_suite import TestSuite
from app.models.taxonomy import (
    Product,
    ProductGroup,
    QADomain,
    SubRequestType,
    System,
    TestCaseComplexity,
    TestCaseType,
)
from app.models.artifact_lineage import ArtifactLineage
from app.models.agent import AgentRun
from app.schemas.test_plan import TestPlanUpdate, TestCaseUpdate
from app.worker.tasks import jira_tasks


# Taxonomy FK fields on TestCase, each validated against its master table by
# existence + is_active (org-wide master data, not project-scoped).
_TAXONOMY_FK_FIELDS: dict[str, type] = {
    "channel_id": System,
    "domain_id": QADomain,
    "area_of_test_id": ProductGroup,
    "product_id": Product,
    "sub_request_type_id": SubRequestType,
    "test_case_type_id": TestCaseType,
    "test_case_complexity_id": TestCaseComplexity,
}


STATUS_VALUES = {"draft", "pending_approval", "approved", "rejected", "automated"}
# Both the new canonical values ("automation") and the legacy ones ("automated",
# "hybrid") are accepted — see notes in the test-cases form for the vocabulary.
MODE_VALUES = {"manual", "automation", "ai", "automated", "hybrid"}
AUTOMATION_ELIGIBLE_VALUES = {"yes", "no"}
AUTOMATION_STATUS_VALUES = {
    # Current canonical values
    "planned_for_automation",
    "ready_for_automation",
    "automated",
    "awaiting_qa_approval",
    # Legacy values still found on older rows
    "not_required",
    "mapping_required",
    "automation_failed",
    "maintenance_required",
}
TEST_PHASE_VALUES = {"SIT", "QA", "UAT", "Regression", "Production Smoke Test"}
TELECOM_DOMAIN_VALUES = {"Mobile", "Fixed", "Digital", "Billing", "Charging", "CRM", "OSS", "BSS", "Middleware", "Integration", "Network", "Data"}
EXTERNAL_TOOL_VALUES = {"Mock", "Playwright", "Pytest", "Katalon", "Selenium", "Other"}
AUTOMATION_RESULT_VALUES = {"pending", "passed", "failed", "skipped", "blocked", "not_run"}
JIRA_SYNC_VALUES = {"synced", "pending", "failed", "conflict", "not_synced"}
JIRA_FINAL_VALUES = {"pending", "passed", "failed", "skipped", "blocked", "not_run"}
AUDITED_FIELDS = {
    "status",
    "priority",
    "execution_mode",
    "automation_eligible",
    "automation_status",
    "automation_ready",
    "external_tool",
    "suite_id",
    "external_tc_id",
    "external_tc_url",
    "jira_final_status",
    "jira_sync_status",
    "telecom_domain",
    "test_phase",
    "test_suite_id",
    "preconditions",
    "steps",
    "expected_result",
    "application_id",
    "metadata_",
    "requirement_id",
    "scenario_id",
    "channel_id",
    "domain_id",
    "area_of_test_id",
    "product_id",
    "sub_request_type_id",
    "test_case_type_id",
    "test_case_complexity_id",
    "test_case_objective",
    "atc_test_case",
    "is_critical",
    "ppm_id",
}


_TESTCASE_EAGER_LOADS = (
    selectinload(TestCase.requirement),
    selectinload(TestCase.test_suite),
    selectinload(TestCase.channel),
    selectinload(TestCase.domain),
    selectinload(TestCase.area_of_test),
    selectinload(TestCase.taxonomy_product),
    selectinload(TestCase.taxonomy_sub_request_type),
    selectinload(TestCase.taxonomy_test_case_type),
    selectinload(TestCase.taxonomy_test_case_complexity),
)


# ── Test Plan ─────────────────────────────────────────────────────────────────

async def list_test_plans(db: AsyncSession, project_id: int) -> list[TestPlan]:
    result = await db.execute(
        select(TestPlan)
        .where(TestPlan.project_id == project_id)
        .order_by(TestPlan.created_at.desc())
    )
    return list(result.scalars().all())


async def get_test_plan(db: AsyncSession, plan_id: int) -> TestPlan | None:
    result = await db.execute(select(TestPlan).where(TestPlan.id == plan_id))
    return result.scalar_one_or_none()


async def update_test_plan(db: AsyncSession, plan: TestPlan, updates: TestPlanUpdate) -> TestPlan:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(plan, key, value)
    await db.flush()
    await db.refresh(plan)
    return plan


async def approve_test_plan(db: AsyncSession, plan: TestPlan, action: str, notes: str | None) -> TestPlan:
    plan.status = "approved" if action == "approve" else "rejected"
    if notes:
        plan.metadata_ = {**(plan.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(plan)
    return plan


# ── Test Scenario ─────────────────────────────────────────────────────────────

async def delete_test_plan(db: AsyncSession, plan: TestPlan) -> None:
    if plan.agent_run_id is not None:
        await db.execute(
            update(AgentRun)
            .where(AgentRun.id == plan.agent_run_id, AgentRun.status == "completed")
            .values(
                status="cancelled",
                output_data=None,
                error_message="Output test plan was deleted.",
                progress_message="Output artifact deleted",
            )
        )
    await db.execute(
        update(TestCase)
        .where(TestCase.linked_test_plan_id == plan.id)
        .values(linked_test_plan_id=None)
    )
    await db.execute(
        delete(ArtifactLineage).where(
            ArtifactLineage.project_id == plan.project_id,
            or_(
                and_(ArtifactLineage.child_type == "test_plan", ArtifactLineage.child_id == plan.id),
                and_(ArtifactLineage.parent_type == "test_plan", ArtifactLineage.parent_id == plan.id),
            ),
        )
    )
    await db.delete(plan)
    await db.flush()


async def list_scenarios(
    db: AsyncSession,
    project_id: int,
    requirement_id: int | None = None,
) -> list[TestScenario]:
    stmt = (
        select(TestScenario)
        .where(TestScenario.project_id == project_id)
        .order_by(TestScenario.created_at.desc())
    )
    if requirement_id:
        stmt = stmt.where(TestScenario.requirement_id == requirement_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_scenario(db: AsyncSession, scenario_id: int) -> TestScenario | None:
    result = await db.execute(select(TestScenario).where(TestScenario.id == scenario_id))
    return result.scalar_one_or_none()


async def approve_test_scenario(db: AsyncSession, scenario: TestScenario, action: str, notes: str | None) -> TestScenario:
    scenario.status = "approved" if action == "approve" else "rejected"
    if notes:
        scenario.metadata_ = {**(scenario.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(scenario)
    return scenario


# ── Test Case ─────────────────────────────────────────────────────────────────

async def list_test_cases(
    db: AsyncSession,
    project_id: int,
    scenario_id: int | None = None,
    requirement_id: int | None = None,
    status: str | None = None,
    automation_only: bool = False,
    skip: int = 0,
    limit: int = 100,
) -> list[TestCase]:
    stmt = (
        select(TestCase)
        .options(*_TESTCASE_EAGER_LOADS)
        .where(TestCase.project_id == project_id)
        .order_by(TestCase.created_at.desc())
    )
    if scenario_id:
        stmt = stmt.where(TestCase.scenario_id == scenario_id)
    if requirement_id:
        stmt = stmt.where(TestCase.requirement_id == requirement_id)
    if status:
        stmt = stmt.where(TestCase.status == status)
    if automation_only:
        stmt = stmt.where(
            func.lower(TestCase.execution_mode).in_(["automation", "automated", "hybrid"]),
            func.lower(TestCase.automation_eligible) == "yes",
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_test_case(db: AsyncSession, tc_id: int) -> TestCase | None:
    result = await db.execute(
        select(TestCase)
        .options(*_TESTCASE_EAGER_LOADS)
        .where(TestCase.id == tc_id)
    )
    return result.scalar_one_or_none()


def _value_to_string(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _validate_enum(field: str, value: str | None, allowed: set[str]) -> None:
    if value is not None and value not in allowed:
        raise HTTPException(status_code=422, detail=f"Invalid {field}: {value}")


def _validate_url(field: str, value: str | None) -> None:
    if not value:
        return
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise HTTPException(status_code=422, detail=f"Invalid {field}")


def _normalize_automation_update(tc: TestCase, data: dict[str, Any]) -> None:
    mode = (data.get("execution_mode", tc.execution_mode) or "").lower()
    eligible = (data.get("automation_eligible", tc.automation_eligible) or "").lower()

    if mode == "manual":
        data["execution_mode"] = "manual"
        data["automation_eligible"] = "no"
        data["automation_status"] = "not_required"
        data["automation_ready"] = False
    elif eligible == "no":
        data["automation_eligible"] = "no"
        data["automation_status"] = "not_required"
        data["automation_ready"] = False
    elif mode == "automated" and eligible == "yes" and data.get("automation_status", tc.automation_status) in {None, "", "not_required"}:
        data["automation_status"] = "mapping_required"


async def _has_execution_results(db: AsyncSession, tc_id: int) -> bool:
    result = await db.execute(
        select(func.count(ExecutionResult.id)).where(ExecutionResult.test_case_id == tc_id)
    )
    return int(result.scalar_one() or 0) > 0


async def _validate_duplicate_external_id(db: AsyncSession, tc: TestCase, data: dict[str, Any]) -> None:
    external_tc_id = data.get("external_tc_id", tc.external_tc_id)
    external_tool = data.get("external_tool", tc.external_tool)
    suite_id = data.get("suite_id", tc.suite_id)
    if not external_tc_id or not external_tool:
        return
    result = await db.execute(
        select(TestCase.id).where(
            TestCase.project_id == tc.project_id,
            TestCase.id != tc.id,
            TestCase.external_tool == external_tool,
            TestCase.external_tc_id == external_tc_id,
            or_(
                TestCase.suite_id == suite_id,
                and_(TestCase.suite_id.is_(None), suite_id is None),
            ),
        )
    )
    if result.scalar_one_or_none() is not None:
        raise HTTPException(status_code=409, detail="external_tc_id already exists for this project/tool/suite")


async def _validate_test_case_update(db: AsyncSession, tc: TestCase, data: dict[str, Any]) -> None:
    if "mode" in data and "execution_mode" not in data:
        data["execution_mode"] = data.pop("mode")
    if "approval_status" in data and "status" not in data:
        data["status"] = data.pop("approval_status")

    _validate_enum("status", data.get("status"), STATUS_VALUES)
    _validate_enum("mode", data.get("execution_mode"), MODE_VALUES)
    _validate_enum("automation_eligible", data.get("automation_eligible"), AUTOMATION_ELIGIBLE_VALUES)
    _validate_enum("automation_status", data.get("automation_status"), AUTOMATION_STATUS_VALUES)
    _validate_enum("test_phase", data.get("test_phase"), TEST_PHASE_VALUES)
    _validate_enum("telecom_domain", data.get("telecom_domain"), TELECOM_DOMAIN_VALUES)
    _validate_enum("external_tool", data.get("external_tool"), EXTERNAL_TOOL_VALUES)
    _validate_enum("last_automation_status", data.get("last_automation_status"), AUTOMATION_RESULT_VALUES)
    _validate_enum("jira_sync_status", data.get("jira_sync_status"), JIRA_SYNC_VALUES)
    _validate_enum("jira_final_status", data.get("jira_final_status"), JIRA_FINAL_VALUES)
    _validate_url("external_tc_url", _value_to_string(data.get("external_tc_url")))
    _validate_url("jira_url", _value_to_string(data.get("jira_url")))

    if "test_suite_id" in data and data["test_suite_id"] is not None:
        suite_result = await db.execute(select(TestSuite).where(TestSuite.id == data["test_suite_id"]))
        suite = suite_result.scalar_one_or_none()
        if suite is None or suite.project_id != tc.project_id:
            raise HTTPException(status_code=422, detail="Test suite not found in this project")

    if "application_id" in data and data["application_id"] is not None:
        application = await db.get(ProjectApplication, data["application_id"])
        if application is None or application.project_id != tc.project_id or not application.is_active:
            raise HTTPException(status_code=422, detail="Active application not found in this project")

    if "requirement_id" in data and data["requirement_id"] is not None:
        requirement = await db.get(Requirement, data["requirement_id"])
        if requirement is None or requirement.project_id != tc.project_id:
            raise HTTPException(status_code=422, detail="Requirement not found in this project")

    if "scenario_id" in data and data["scenario_id"] is not None:
        scenario = await db.get(TestScenario, data["scenario_id"])
        if scenario is None or scenario.project_id != tc.project_id:
            raise HTTPException(status_code=422, detail="Scenario not found in this project")
        requested_requirement_id = data.get("requirement_id", tc.requirement_id)
        if scenario.requirement_id is not None and requested_requirement_id != scenario.requirement_id:
            raise HTTPException(status_code=422, detail="Scenario is not linked to the selected requirement")

    for field, model in _TAXONOMY_FK_FIELDS.items():
        if field in data and data[field] is not None:
            entity = await db.get(model, data[field])
            if entity is None or not entity.is_active:
                raise HTTPException(status_code=422, detail=f"Invalid or inactive {field}")

    mode = data.get("execution_mode", tc.execution_mode)
    eligible = data.get("automation_eligible", tc.automation_eligible)
    automation_status = data.get("automation_status", tc.automation_status)
    external_tc_id = data.get("external_tc_id", tc.external_tc_id)
    automation_script_id = data.get("automation_script_id", tc.automation_script_id)

    # "Automated" status is valid for any non-manual mode (automation / automated /
    # ai / hybrid). The historical check only allowed "automated", which broke
    # rows saved with the new "automation" vocabulary.
    if automation_status == "automated" and mode == "manual":
        raise HTTPException(status_code=422, detail="Automated status requires a non-manual execution mode")
    if automation_status == "automated" and eligible != "yes":
        raise HTTPException(status_code=422, detail="Automated status requires automation_eligible yes")
    # Internal tools (Playwright / Pytest) generate and link the script through
    # the platform's automation pipeline, so requiring an external_tc_id up-front
    # would block legitimate automated rows. External tools (Katalon, Selenium,
    # etc.) still need either an external ID or an attached script — that's the
    # only way the platform can correlate runs back to this row.
    external_tool = (data.get("external_tool", tc.external_tool) or "")
    is_internal_tool = external_tool in {"Playwright", "Pytest"}
    if automation_status == "automated" and not is_internal_tool \
            and not external_tc_id and not automation_script_id:
        raise HTTPException(
            status_code=422,
            detail="Automated status needs an external_tc_id, a linked automation_script_id, "
                   "or an internal tool (Playwright / Pytest) selected as External Tool",
        )
    if data.get("status") == "approved" and not (data.get("title") or tc.title):
        raise HTTPException(status_code=422, detail="Approved test cases require a title")
    if data.get("status") == "rejected" and not (data.get("comment") or (tc.metadata_ or {}).get("review_notes")):
        raise HTTPException(status_code=422, detail="Rejected test cases require a comment")
    if "title" in data and await _has_execution_results(db, tc.id):
        raise HTTPException(status_code=409, detail="Cannot change title after execution results exist")
    if data.get("jira_sync_status", tc.jira_sync_status) == "conflict" and data.get("jira_final_status") is not None:
        raise HTTPException(status_code=409, detail="Resolve Jira sync conflict before changing Jira final status")
    await _validate_duplicate_external_id(db, tc, data)


async def update_test_case(
    db: AsyncSession,
    tc: TestCase,
    updates: TestCaseUpdate,
    *,
    user_id: int | None = None,
    source: str = "platform",
) -> TestCase:
    data = updates.model_dump(exclude_unset=True)
    comment = data.pop("comment", None)
    data = {
        key: (str(value) if key in {"external_tc_url", "jira_url"} and value is not None else value)
        for key, value in data.items()
    }
    if "mode" in data and "execution_mode" not in data:
        data["execution_mode"] = data.pop("mode")
    if "approval_status" in data and "status" not in data:
        data["status"] = data.pop("approval_status")
    if data.get("automation_status") == "automated" and data.get("execution_mode") == "manual":
        raise HTTPException(status_code=422, detail="Manual test cases cannot be marked automated")
    if data.get("automation_status") == "automated" and data.get("automation_eligible") == "no":
        raise HTTPException(status_code=422, detail="Automation-ineligible test cases cannot be marked automated")
    _normalize_automation_update(tc, data)
    validation_data = {**data, "comment": comment}
    await _validate_test_case_update(db, tc, validation_data)
    now = datetime.now(timezone.utc)
    changed: list[tuple[str, Any, Any]] = []
    for key, value in data.items():
        old_value = getattr(tc, key)
        if old_value == value:
            continue
        setattr(tc, key, value)
        if key in AUDITED_FIELDS:
            changed.append((key, old_value, value))
    if changed:
        tc.updated_by = user_id
    if any(field == "status" for field, _, _ in changed):
        tc.last_status_updated_by = user_id
        tc.last_status_updated_at = now
    if any(field in {"execution_mode", "automation_eligible"} for field, _, _ in changed):
        await deactivate_active_mappings_if_not_automation_applicable(db, tc)
    for field, old_value, new_value in changed:
        db.add(TestCaseHistory(
            project_id=tc.project_id,
            test_case_id=tc.id,
            changed_by=user_id,
            field_name=field,
            old_value=_value_to_string(old_value),
            new_value=_value_to_string(new_value),
            source=source,
            comment=comment,
        ))
    await db.flush()
    await db.refresh(tc)
    return tc


async def deactivate_active_mappings_if_not_automation_applicable(db: AsyncSession, tc: TestCase) -> None:
    mode = (tc.execution_mode or "").lower()
    eligible = (tc.automation_eligible or "").lower()
    # Accept new ("automation") and legacy ("automated") mode values + AI flow.
    if mode in {"automation", "automated", "ai"} and eligible == "yes":
        return
    result = await db.execute(
        select(AutomationTestMapping).where(
            AutomationTestMapping.project_id == tc.project_id,
            AutomationTestMapping.test_case_id == tc.id,
            AutomationTestMapping.is_active.is_(True),
        )
    )
    for mapping in result.scalars().all():
        mapping.is_active = False
        mapping.automation_status = "not_required"


async def bulk_update_test_cases(
    db: AsyncSession,
    *,
    test_case_ids: list[int],
    project_id: int,
    patch: dict[str, Any],
    reason: str,
    user_id: int,
    dry_run: bool,
) -> dict[str, Any]:
    """Apply the same field patch to many test cases in a single transaction.

    Per-row outcomes:
        - updated: at least one field changed; new state persisted (if dry_run=false)
        - skipped: row's current state already matches the patch (no diff)
        - conflict: applying the patch would silently corrupt state — see reason
                    (e.g. flipping mode→manual on a row with a linked automation script)
        - not_found: id wasn't in the DB
        - forbidden: row belongs to a different project than the caller's claim

    Conflict rows are NEVER mutated, even when dry_run is false. The caller decides
    whether to retry per-row after manual cleanup.

    The function returns the analysis structure regardless of dry_run; only the
    mutation step is skipped when dry_run is true.
    """
    # Strip None values so we only operate on fields the caller intends to set.
    effective_patch: dict[str, Any] = {k: v for k, v in patch.items() if v is not None}

    # Belt-and-braces enum validation. The frontend dropdowns only offer valid
    # values, but a direct API caller could otherwise persist garbage that the
    # single-row update flow would have rejected.
    _ENUM_CHECKS: list[tuple[str, set[str]]] = [
        ("execution_mode", MODE_VALUES),
        ("automation_status", AUTOMATION_STATUS_VALUES),
        # External tool accepts an explicit empty-string "clear" value in addition to the enum.
        ("external_tool", EXTERNAL_TOOL_VALUES | {""}),
    ]
    for field, allowed in _ENUM_CHECKS:
        if field in effective_patch and effective_patch[field] not in allowed:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid value '{effective_patch[field]}' for {field}. Allowed: {sorted(allowed)}",
            )

    if "test_suite_id" in effective_patch:
        suite_result = await db.execute(select(TestSuite).where(TestSuite.id == effective_patch["test_suite_id"]))
        suite = suite_result.scalar_one_or_none()
        if suite is None or suite.project_id != project_id:
            raise HTTPException(status_code=422, detail="Test suite not found in this project")

    # Dedupe the id list while preserving order. A naive call with `[1, 1, 1]`
    # would otherwise iterate the same row three times — once "updated" and
    # twice "skipped" — and inflate every counter in the summary.
    deduped_ids: list[int] = list(dict.fromkeys(test_case_ids))

    if not effective_patch:
        return {
            "requested": len(deduped_ids),
            "updated": 0,
            "skipped": len(deduped_ids),
            "conflicts": 0,
            "not_found": 0,
            "forbidden": 0,
            "dry_run": dry_run,
            "rows": [
                {"test_case_id": tc_id, "outcome": "skipped", "changes": {},
                 "conflict_reason": "patch was empty"}
                for tc_id in deduped_ids
            ],
        }

    # Fetch all requested rows in one round-trip.
    fetched = await db.execute(select(TestCase).where(TestCase.id.in_(deduped_ids)))
    by_id: dict[int, TestCase] = {tc.id: tc for tc in fetched.scalars().all()}

    rows: list[dict[str, Any]] = []
    counts = {"updated": 0, "skipped": 0, "conflicts": 0, "not_found": 0, "forbidden": 0}

    for tc_id in deduped_ids:
        tc = by_id.get(tc_id)
        if tc is None:
            counts["not_found"] += 1
            rows.append({
                "test_case_id": tc_id, "outcome": "not_found",
                "changes": {}, "conflict_reason": "Test case does not exist",
            })
            continue
        if tc.project_id != project_id:
            counts["forbidden"] += 1
            rows.append({
                "test_case_id": tc_id, "test_case_key": tc.test_case_id, "title": tc.title,
                "outcome": "forbidden", "changes": {},
                "conflict_reason": f"Test case belongs to project {tc.project_id}, not {project_id}",
            })
            continue

        # Conflict detection: switching mode → manual on a TC with an
        # attached automation script silently orphans the script. Block it
        # so the caller can detach explicitly.
        new_mode = effective_patch.get("execution_mode")
        if new_mode == "manual" and tc.automation_script_id is not None:
            counts["conflicts"] += 1
            rows.append({
                "test_case_id": tc.id, "test_case_key": tc.test_case_id, "title": tc.title,
                "outcome": "conflict", "changes": {},
                "conflict_reason": f"Has linked automation script #{tc.automation_script_id} — detach it before switching to Manual",
            })
            continue
        # Manual + Automated status doesn't make sense.
        if effective_patch.get("automation_status") == "automated" and \
                (new_mode == "manual" or (new_mode is None and (tc.execution_mode or "").lower() == "manual")):
            counts["conflicts"] += 1
            rows.append({
                "test_case_id": tc.id, "test_case_key": tc.test_case_id, "title": tc.title,
                "outcome": "conflict", "changes": {},
                "conflict_reason": "Cannot mark a Manual test case as Automated",
            })
            continue

        # Build per-row diff (only fields whose value would actually change).
        diff: dict[str, dict[str, Any]] = {}
        for field, new_value in effective_patch.items():
            old_value = getattr(tc, field, None)
            if old_value == new_value:
                continue
            diff[field] = {"old": old_value, "new": new_value}

        if not diff:
            counts["skipped"] += 1
            rows.append({
                "test_case_id": tc.id, "test_case_key": tc.test_case_id, "title": tc.title,
                "outcome": "skipped", "changes": {},
            })
            continue

        # Auto-derive automation_eligible from mode when mode is in the patch,
        # mirroring the single-row form's cross-field behaviour.
        if new_mode is not None:
            derived_eligible = "no" if new_mode == "manual" else "yes"
            if tc.automation_eligible != derived_eligible:
                diff["automation_eligible"] = {"old": tc.automation_eligible, "new": derived_eligible}

        counts["updated"] += 1

        if not dry_run:
            now = datetime.now(timezone.utc)
            for field, change in diff.items():
                setattr(tc, field, change["new"])
                if field in AUDITED_FIELDS:
                    db.add(TestCaseHistory(
                        project_id=tc.project_id,
                        test_case_id=tc.id,
                        changed_by=user_id,
                        field_name=field,
                        old_value=_value_to_string(change["old"]),
                        new_value=_value_to_string(change["new"]),
                        source="bulk_update",
                        comment=reason,
                    ))
            tc.updated_by = user_id
            if "status" in diff:
                tc.last_status_updated_by = user_id
                tc.last_status_updated_at = now
            if "execution_mode" in diff or "automation_eligible" in diff:
                await deactivate_active_mappings_if_not_automation_applicable(db, tc)

        rows.append({
            "test_case_id": tc.id, "test_case_key": tc.test_case_id, "title": tc.title,
            "outcome": "updated", "changes": diff,
        })

    if not dry_run:
        await db.flush()

    return {
        # `requested` reflects unique IDs analysed — duplicates are folded in
        # so callers can rely on `requested == sum(per-outcome-counters)`.
        "requested": len(deduped_ids),
        **counts,
        "dry_run": dry_run,
        "rows": rows,
    }


async def approve_test_case(db: AsyncSession, tc: TestCase, action: str, notes: str | None, user_id: int | None = None) -> TestCase:
    previous = tc.status
    tc.status = "approved" if action == "approve" else "rejected"
    if notes:
        tc.metadata_ = {**(tc.metadata_ or {}), "review_notes": notes}
    if previous != tc.status:
        now = datetime.now(timezone.utc)
        tc.updated_by = user_id
        tc.last_status_updated_by = user_id
        tc.last_status_updated_at = now
        db.add(TestCaseHistory(
            project_id=tc.project_id,
            test_case_id=tc.id,
            changed_by=user_id,
            field_name="status",
            old_value=previous,
            new_value=tc.status,
            source="platform",
            comment=notes,
        ))
    await db.flush()
    await db.refresh(tc)
    return tc


async def count_test_cases_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(TestCase.status, func.count())
        .where(TestCase.project_id == project_id)
        .group_by(TestCase.status)
    )
    return {row[0]: row[1] for row in result.all()}


async def test_case_summary(db: AsyncSession, project_id: int) -> dict[str, Any]:
    async def grouped(column) -> dict[str, int]:
        result = await db.execute(
            select(column, func.count())
            .where(TestCase.project_id == project_id)
            .group_by(column)
        )
        return {str(key or "unassigned"): int(value) for key, value in result.all()}

    total_result = await db.execute(select(func.count(TestCase.id)).where(TestCase.project_id == project_id))
    by_status = await grouped(TestCase.status)
    return {
        "total": int(total_result.scalar_one() or 0),
        "by_status": by_status,
        "by_approval_status": by_status,
        "by_automation_status": await grouped(TestCase.automation_status),
        "by_mode": await grouped(TestCase.execution_mode),
        "by_jira_sync_status": await grouped(TestCase.jira_sync_status),
        "by_priority": await grouped(TestCase.priority),
        "by_telecom_domain": await grouped(TestCase.telecom_domain),
    }


async def list_test_case_history(db: AsyncSession, tc: TestCase) -> list[TestCaseHistory]:
    result = await db.execute(
        select(TestCaseHistory)
        .where(TestCaseHistory.test_case_id == tc.id, TestCaseHistory.project_id == tc.project_id)
        .order_by(TestCaseHistory.created_at.desc(), TestCaseHistory.id.desc())
    )
    return list(result.scalars().all())


async def sync_test_case_jira(db: AsyncSession, tc: TestCase, user_id: int) -> tuple[int | None, str | None]:
    result = await db.execute(
        select(JiraConnection)
        .where(JiraConnection.project_id == tc.project_id, JiraConnection.is_active.is_(True))
        .order_by(JiraConnection.updated_at.desc())
    )
    connection = result.scalars().first()
    if connection is None:
        old_status = tc.jira_sync_status
        tc.jira_sync_status = "failed"
        tc.jira_sync_error = "No active Jira connection configured"
        db.add(TestCaseHistory(
            project_id=tc.project_id,
            test_case_id=tc.id,
            changed_by=user_id,
            field_name="jira_sync_status",
            old_value=old_status,
            new_value="failed",
            source="platform",
            comment=tc.jira_sync_error,
        ))
        await db.flush()
        raise HTTPException(status_code=409, detail=tc.jira_sync_error)

    old_status = tc.jira_sync_status
    tc.jira_sync_status = "pending"
    tc.jira_sync_error = None
    tc.jira_last_synced_at = datetime.now(timezone.utc)
    history = JiraSyncHistory(
        project_id=tc.project_id,
        connection_id=connection.id,
        triggered_by=user_id,
        direction="outbound",
        status="queued",
        metadata_={"test_case_id": tc.id, "jira_issue_key": tc.jira_issue_key},
    )
    db.add(history)
    db.add(TestCaseHistory(
        project_id=tc.project_id,
        test_case_id=tc.id,
        changed_by=user_id,
        field_name="jira_sync_status",
        old_value=old_status,
        new_value="pending",
        source="platform",
        comment="Queued Jira sync",
    ))
    await db.flush()
    task = jira_tasks.outbound_sync.delay(connection.id, history.id, user_id)
    history.celery_task_id = task.id
    await db.flush()
    return history.id, task.id
