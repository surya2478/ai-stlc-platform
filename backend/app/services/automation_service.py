"""Automation Script service — CRUD operations."""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.integrations.automation.connector_factory import get_automation_connector
from app.integrations.automation.result_normalizer import normalize_status
from app.models.automation_mapping import AutomationTestMapping
from app.models.automation_script import AutomationScript
from app.models.execution import ExecutionResult, ExecutionRun
from app.models.test_case import TestCase
from app.schemas.automation import AutomationScriptUpdate, AutomationTestMappingCreate, AutomationTestMappingUpdate
from app.services import traceability_service
from app.services.display_id_service import display_id, temporary_id


async def list_scripts(
    db: AsyncSession,
    project_id: int,
    test_case_id: int | None = None,
    status: str | None = None,
) -> list[AutomationScript]:
    stmt = (
        select(AutomationScript)
        .where(AutomationScript.project_id == project_id)
        .order_by(AutomationScript.created_at.desc())
    )
    if test_case_id:
        stmt = stmt.where(AutomationScript.test_case_id == test_case_id)
    if status:
        stmt = stmt.where(AutomationScript.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_script(db: AsyncSession, script_id: int) -> AutomationScript | None:
    result = await db.execute(
        select(AutomationScript).where(AutomationScript.id == script_id)
    )
    return result.scalar_one_or_none()


async def update_script(
    db: AsyncSession, script: AutomationScript, updates: AutomationScriptUpdate
) -> AutomationScript:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(script, key, value)
    await db.flush()
    await db.refresh(script)
    return script


async def approve_script(
    db: AsyncSession, script: AutomationScript, action: str, notes: str | None
) -> AutomationScript:
    script.status = "approved" if action == "approve" else "rejected"
    if notes:
        script.metadata_ = {**(script.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(script)
    return script


async def count_scripts_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(AutomationScript.status, func.count())
        .where(AutomationScript.project_id == project_id)
        .group_by(AutomationScript.status)
    )
    return {row[0]: row[1] for row in result.all()}


async def get_test_case_or_404(db: AsyncSession, test_case_id: int) -> TestCase:
    result = await db.execute(select(TestCase).where(TestCase.id == test_case_id))
    test_case = result.scalar_one_or_none()
    if not test_case:
        raise HTTPException(status_code=404, detail="Test case not found")
    return test_case


async def get_mapping(db: AsyncSession, mapping_id: int) -> AutomationTestMapping | None:
    result = await db.execute(select(AutomationTestMapping).where(AutomationTestMapping.id == mapping_id))
    return result.scalar_one_or_none()


async def list_mappings(
    db: AsyncSession,
    *,
    project_id: int,
    test_case_id: int | None = None,
    active_only: bool = False,
) -> list[AutomationTestMapping]:
    stmt = select(AutomationTestMapping).where(AutomationTestMapping.project_id == project_id)
    if test_case_id is not None:
        stmt = stmt.where(AutomationTestMapping.test_case_id == test_case_id)
    if active_only:
        stmt = stmt.where(AutomationTestMapping.is_active.is_(True))
    stmt = stmt.order_by(AutomationTestMapping.updated_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def active_mapping_for_test_case(db: AsyncSession, *, project_id: int, test_case_id: int) -> AutomationTestMapping | None:
    result = await db.execute(
        select(AutomationTestMapping).where(
            AutomationTestMapping.project_id == project_id,
            AutomationTestMapping.test_case_id == test_case_id,
            AutomationTestMapping.is_active.is_(True),
        )
    )
    return result.scalars().first()


def _validate_automatable_test_case(test_case: TestCase) -> None:
    if (test_case.execution_mode or "").lower() != "automated":
        raise HTTPException(status_code=422, detail="Test case must be automated before using automation")
    if (test_case.automation_eligible or "").lower() != "yes":
        raise HTTPException(status_code=422, detail="Test case is not automation eligible")


def _sync_mapping_to_test_case(test_case: TestCase, mapping: AutomationTestMapping) -> None:
    test_case.execution_mode = "automated" if test_case.execution_mode == "manual" else test_case.execution_mode
    test_case.automation_eligible = "yes"
    test_case.automation_status = mapping.automation_status
    test_case.automation_ready = bool(mapping.is_active)
    test_case.external_tool = mapping.external_tool_name
    test_case.suite_id = mapping.external_suite_id
    test_case.external_tc_id = mapping.external_test_case_id
    test_case.automation_script_id = int(mapping.external_script_id) if (mapping.external_script_id or "").isdigit() else test_case.automation_script_id


async def create_mapping(db: AsyncSession, body: AutomationTestMappingCreate) -> AutomationTestMapping:
    test_case = await get_test_case_or_404(db, body.test_case_id)
    if test_case.project_id != body.project_id:
        raise HTTPException(status_code=403, detail="Test case does not belong to this project")
    _validate_automatable_test_case(test_case)
    mapping = AutomationTestMapping(**body.model_dump())
    db.add(mapping)
    await db.flush()
    _sync_mapping_to_test_case(test_case, mapping)
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def update_mapping(db: AsyncSession, mapping: AutomationTestMapping, updates: AutomationTestMappingUpdate) -> AutomationTestMapping:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(mapping, key, value)
    result = await db.execute(select(TestCase).where(TestCase.id == mapping.test_case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        _sync_mapping_to_test_case(test_case, mapping)
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def deactivate_mapping(db: AsyncSession, mapping: AutomationTestMapping) -> AutomationTestMapping:
    mapping.is_active = False
    result = await db.execute(select(TestCase).where(TestCase.id == mapping.test_case_id))
    test_case = result.scalar_one_or_none()
    if test_case:
        test_case.automation_ready = False
        test_case.automation_status = "mapping_required" if test_case.execution_mode in {"automated", "hybrid"} else "not_required"
    await db.flush()
    await db.refresh(mapping)
    return mapping


async def run_external_automation(
    db: AsyncSession,
    *,
    project_id: int,
    test_case_ids: list[int],
    environment: str,
    user_id: int,
) -> ExecutionRun:
    mappings = []
    test_cases_by_id = {}
    for test_case_id in test_case_ids:
        test_case = await get_test_case_or_404(db, test_case_id)
        if test_case.project_id != project_id:
            raise HTTPException(status_code=403, detail=f"Test case {test_case_id} does not belong to this project")
        _validate_automatable_test_case(test_case)
        mapping = await active_mapping_for_test_case(db, project_id=project_id, test_case_id=test_case_id)
        if not mapping:
            raise HTTPException(status_code=422, detail=f"Active automation mapping required for {test_case.test_case_id}")
        mappings.append(mapping)
        test_cases_by_id[test_case_id] = test_case

    now = datetime.now(timezone.utc)
    run = ExecutionRun(
        project_id=project_id,
        created_by=user_id,
        triggered_by=user_id,
        execution_id=temporary_id("ER"),
        source_type="external_automation_tool",
        external_tool_name=mappings[0].external_tool_name if mappings else None,
        environment=environment,
        status="running",
        started_at=now,
        total_tests=len(mappings),
        passed=0,
        failed=0,
        skipped=0,
        execution_logs=[],
    )
    db.add(run)
    await db.flush()
    run.execution_id = display_id("ER", run.id)

    result_ids = []
    all_logs = []
    external_run_ids = []
    for mapping in mappings:
        connector = get_automation_connector(mapping.external_tool_name)
        summary = await connector.trigger_execution(mapping, environment)
        external_run_ids.append(summary.external_run_id)
        for external_result in summary.results:
            test_case = test_cases_by_id[mapping.test_case_id]
            status = normalize_status(external_result.status)
            exec_result = ExecutionResult(
                execution_run_id=run.id,
                project_id=project_id,
                test_case_id=mapping.test_case_id,
                automation_mapping_id=mapping.id,
                test_name=test_case.title,
                status=status,
                execution_mode=test_case.execution_mode,
                external_tool_name=mapping.external_tool_name,
                external_test_case_id=mapping.external_test_case_id,
                automation_execution_status=status,
                manual_execution_status="pending" if test_case.execution_mode == "hybrid" else None,
                jira_execution_status=None,
                duration_seconds=external_result.duration_seconds,
                duration_ms=int(external_result.duration_seconds * 1000),
                error_message=external_result.error_message,
                stack_trace=external_result.stack_trace,
                screenshot_url=external_result.screenshot_url,
                video_url=external_result.video_url,
                log_url=external_result.log_url,
                external_result_url=external_result.external_result_url,
                jira_issue_key=test_case.jira_issue_key,
                jira_test_key=test_case.jira_test_key,
                raw_result_json=external_result.raw,
                logs=external_result.logs,
            )
            db.add(exec_result)
            await db.flush()
            await traceability_service.create_lineage_many(
                db,
                project_id=project_id,
                parents=[("test_case", mapping.test_case_id), ("execution_run", run.id)],
                child_type="execution_result",
                child_id=exec_result.id,
                metadata={"automation_mapping_id": mapping.id, "source": "external_automation_tool"},
            )
            result_ids.append(exec_result.id)
            all_logs.extend(external_result.logs)
            mapping.last_synced_at = now
            mapping.automation_status = "automated" if status in {"passed", "failed", "skipped"} else mapping.automation_status
            test_case.automation_status = mapping.automation_status
            test_case.last_automation_status = status
            test_case.last_automation_run_at = now
            test_case.last_execution_run_id = run.id
            test_case.latest_evidence_available = bool(external_result.log_url or external_result.screenshot_url or external_result.video_url)
            test_case.evidence_url = external_result.log_url or external_result.screenshot_url or external_result.video_url

    run.external_run_id = ",".join(external_run_ids)
    run.status = "completed"
    run.completed_at = datetime.now(timezone.utc)
    run.duration_seconds = max((run.completed_at - run.started_at).total_seconds(), 0.0) if run.started_at else None
    run.execution_logs = all_logs
    run.total_tests = len(result_ids)
    run.passed = await _count_results(db, run.id, "passed")
    run.failed = await _count_results(db, run.id, "failed")
    run.skipped = await _count_results(db, run.id, "skipped")
    run.metadata_ = {"result_ids": result_ids, "final_status_source": "jira"}
    await db.flush()
    await db.refresh(run)
    return run


async def sync_external_automation_result(
    db: AsyncSession,
    *,
    mapping: AutomationTestMapping,
    environment: str,
    user_id: int,
) -> ExecutionRun:
    if not mapping.is_active:
        raise HTTPException(status_code=422, detail="Automation mapping is inactive")
    return await run_external_automation(
        db,
        project_id=mapping.project_id,
        test_case_ids=[mapping.test_case_id],
        environment=environment,
        user_id=user_id,
    )


async def execution_history(db: AsyncSession, *, test_case_id: int) -> list[ExecutionResult]:
    stmt = (
        select(ExecutionResult)
        .where(ExecutionResult.test_case_id == test_case_id)
        .order_by(ExecutionResult.created_at.desc())
        .limit(100)
    )
    return list((await db.execute(stmt)).scalars().all())


async def sync_jira_execution_status(
    db: AsyncSession,
    *,
    test_case_id: int,
    jira_execution_status: str,
    jira_issue_key: str | None,
    jira_test_key: str | None,
) -> ExecutionResult:
    status = normalize_status(jira_execution_status)
    test_case = await get_test_case_or_404(db, test_case_id)
    if jira_issue_key:
        test_case.jira_issue_key = jira_issue_key
    if jira_test_key:
        test_case.jira_test_key = jira_test_key
    test_case.jira_final_status = status
    test_case.jira_sync_status = "synced"
    test_case.jira_last_synced_at = datetime.now(timezone.utc)
    test_case.jira_sync_error = None

    latest = (
        await db.execute(
            select(ExecutionResult)
            .where(ExecutionResult.test_case_id == test_case_id)
            .order_by(ExecutionResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if latest is None:
        run = ExecutionRun(
            project_id=test_case.project_id,
            created_by=test_case.created_by,
            execution_id=temporary_id("ER"),
            source_type="jira_sync",
            status="completed",
            total_tests=1,
            passed=0,
            failed=0,
            skipped=0,
            completed_at=datetime.now(timezone.utc),
        )
        db.add(run)
        await db.flush()
        run.execution_id = display_id("ER", run.id)
        latest = ExecutionResult(
            execution_run_id=run.id,
            project_id=test_case.project_id,
            test_case_id=test_case.id,
            test_name=test_case.title,
            status=status,
            execution_mode=test_case.execution_mode,
        )
        db.add(latest)
    latest.jira_execution_status = status
    latest.jira_issue_key = jira_issue_key or latest.jira_issue_key or test_case.jira_issue_key
    latest.jira_test_key = jira_test_key or latest.jira_test_key or test_case.jira_test_key
    latest.status = status
    latest.metadata_ = {**(latest.metadata_ or {}), "final_status_source": "jira", "jira_synced_at": datetime.now(timezone.utc).isoformat()}
    await db.flush()
    await db.refresh(latest)
    return latest


async def latest_jira_execution_status(db: AsyncSession, *, test_case_id: int) -> dict:
    latest = (
        await db.execute(
            select(ExecutionResult)
            .where(ExecutionResult.test_case_id == test_case_id)
            .order_by(ExecutionResult.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    test_case = await get_test_case_or_404(db, test_case_id)
    jira_status = latest.jira_execution_status if latest else None
    return {
        "test_case_id": test_case_id,
        "jira_issue_key": (latest.jira_issue_key if latest else None) or test_case.jira_issue_key,
        "jira_test_key": (latest.jira_test_key if latest else None) or test_case.jira_test_key,
        "jira_execution_status": jira_status or test_case.jira_final_status,
        "final_qa_status": jira_status or test_case.jira_final_status or "Pending Jira Status",
        "source": "jira",
    }


async def _count_results(db: AsyncSession, run_id: int, status: str) -> int:
    return int(
        (
            await db.execute(
                select(func.count()).select_from(ExecutionResult).where(
                    ExecutionResult.execution_run_id == run_id,
                    ExecutionResult.automation_execution_status == status,
                )
            )
        ).scalar_one()
    )
