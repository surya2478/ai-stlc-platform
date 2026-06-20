"""
Test Plan, Test Scenario, and Test Case service — CRUD operations.
"""
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import selectinload

from app.models.automation_mapping import AutomationTestMapping
from app.models.execution import ExecutionResult
from app.models.jira_connection import JiraConnection
from app.models.jira_sync import JiraSyncHistory
from app.models.test_plan import TestPlan
from app.models.test_scenario import TestScenario
from app.models.test_case import TestCase, TestCaseHistory
from app.schemas.test_plan import TestPlanUpdate, TestCaseUpdate
from app.worker.tasks import jira_tasks


STATUS_VALUES = {"draft", "pending_approval", "approved", "rejected", "automated"}
MODE_VALUES = {"manual", "automated", "hybrid", "ai"}
AUTOMATION_ELIGIBLE_VALUES = {"yes", "no"}
AUTOMATION_STATUS_VALUES = {
    "not_required",
    "mapping_required",
    "ready_for_automation",
    "automated",
    "automation_failed",
    "maintenance_required",
}
TEST_PHASE_VALUES = {"SIT", "UAT", "Regression", "NFT", "Production_Validation"}
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
}


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
        .options(selectinload(TestCase.requirement))
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
            func.lower(TestCase.execution_mode) == "automated",
            func.lower(TestCase.automation_eligible) == "yes",
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_test_case(db: AsyncSession, tc_id: int) -> TestCase | None:
    result = await db.execute(
        select(TestCase)
        .options(selectinload(TestCase.requirement))
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

    mode = data.get("execution_mode", tc.execution_mode)
    eligible = data.get("automation_eligible", tc.automation_eligible)
    automation_status = data.get("automation_status", tc.automation_status)
    external_tc_id = data.get("external_tc_id", tc.external_tc_id)
    automation_script_id = data.get("automation_script_id", tc.automation_script_id)

    if automation_status == "automated" and mode != "automated":
        raise HTTPException(status_code=422, detail="Automated status requires mode automated")
    if automation_status == "automated" and eligible != "yes":
        raise HTTPException(status_code=422, detail="Automated status requires automation_eligible yes")
    if automation_status == "automated" and not external_tc_id and not automation_script_id:
        raise HTTPException(status_code=422, detail="Automated status requires external_tc_id or automation_script_id")
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
    if (tc.execution_mode or "").lower() == "automated" and (tc.automation_eligible or "").lower() == "yes":
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
