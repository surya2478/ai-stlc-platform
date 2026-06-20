"""Service layer for Test Data Management."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_data import TestData, TestDataTemplate
from app.schemas.test_data import (
    TestDataCreate,
    TestDataMaskRequest,
    TestDataTemplateCreate,
    TestDataTemplateUpdate,
    TestDataUpdate,
)
from app.services import approval_service, traceability_service
from app.services.display_id_service import display_id, temporary_id


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _normalize_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    return payload if isinstance(payload, dict) else {}


def _preview_payload(payload: dict[str, Any], sensitive_fields: list[str]) -> dict[str, Any]:
    preview: dict[str, Any] = {}
    for key, value in payload.items():
        if key in sensitive_fields:
            preview[key] = "***"
        else:
            preview[key] = value
    return preview


def _mask_value(value: Any, keep_last: int = 3) -> Any:
    if not isinstance(value, str):
        return value
    if "@" in value and "." in value.split("@")[-1]:
        name, domain = value.split("@", 1)
        if not name:
            return f"***@{domain}"
        return f"{name[0]}***@{domain}"
    if len(value) <= keep_last:
        return "X" * len(value)
    prefix_len = min(5, max(1, len(value) - keep_last - 4))
    suffix = value[-keep_last:]
    return f"{value[:prefix_len]}{'X' * max(4, len(value) - prefix_len - keep_last)}{suffix}"


def _mask_payload(payload: dict[str, Any], fields: list[str], keep_last: int) -> dict[str, Any]:
    masked = dict(payload)
    for field in fields:
        if field in masked:
            masked[field] = _mask_value(masked[field], keep_last=keep_last)
    return masked


def _quality_check(item: TestData) -> tuple[float, str, list[dict[str, Any]]]:
    issues: list[dict[str, Any]] = []
    payload = _normalize_payload(item.data_payload_json)

    if not payload:
        issues.append({"code": "missing_payload", "message": "Data payload is empty."})

    required_fields = _as_list(_as_dict(item.validation_rules_json).get("required_fields"))
    for field in required_fields:
        if field not in payload or payload.get(field) in (None, ""):
            issues.append({"code": "required_field_missing", "field": field, "message": f"Required field '{field}' is missing."})

    if item.contains_pii and item.masking_status == "not_required":
        issues.append({"code": "masking_required", "message": "PII data must not remain in not_required masking state."})

    if item.status in {"draft", "rejected", "expired"}:
        issues.append({"code": "not_execution_ready", "message": f"Status '{item.status}' is not execution-ready."})

    if item.reservation_status == "reserved" and item.reservation_expires_at and item.reservation_expires_at <= now_utc():
        issues.append({"code": "reservation_expired", "message": "Reservation has expired."})

    score = max(0.0, 100.0 - (len(issues) * 20.0))
    if not issues:
        return score, "valid", issues
    if any(issue["code"] in {"missing_payload", "masking_required"} for issue in issues):
        return score, "invalid", issues
    return score, "warning", issues


def _ensure_allowed_status_transition(current: str, target: str) -> None:
    allowed: dict[str, set[str]] = {
        "draft": {"draft", "pending_approval", "archived", "invalid"},
        "pending_approval": {"approved", "rejected", "draft", "archived", "invalid"},
        "approved": {"active", "reserved", "archived", "invalid"},
        "active": {"reserved", "consumed", "expired", "archived", "invalid"},
        "reserved": {"active", "released", "consumed", "expired"},
        "consumed": {"archived"},
        "released": {"active", "reserved", "archived"},
        "expired": {"archived"},
        "rejected": {"draft", "archived"},
        "archived": {"archived"},
        "invalid": {"draft", "archived"},
    }
    if target not in allowed.get(current, {current}):
        raise HTTPException(status_code=409, detail=f"Invalid status transition from '{current}' to '{target}'")


async def list_test_data(
    db: AsyncSession,
    project_id: int,
    *,
    status: str | None = None,
    source_type: str | None = None,
    reservation_status: str | None = None,
) -> list[TestData]:
    stmt = select(TestData).where(TestData.project_id == project_id).order_by(TestData.updated_at.desc())
    if status:
        stmt = stmt.where(TestData.status == status)
    if source_type:
        stmt = stmt.where(TestData.source_type == source_type)
    if reservation_status:
        stmt = stmt.where(TestData.reservation_status == reservation_status)
    return list((await db.execute(stmt)).scalars().all())


async def get_test_data(db: AsyncSession, item_id: int) -> TestData | None:
    return (await db.execute(select(TestData).where(TestData.id == item_id))).scalar_one_or_none()


async def get_template(db: AsyncSession, template_id: int) -> TestDataTemplate | None:
    return (await db.execute(select(TestDataTemplate).where(TestDataTemplate.id == template_id))).scalar_one_or_none()


async def _validate_project_links(db: AsyncSession, project_id: int, requirement_id: int | None, test_case_id: int | None) -> None:
    if requirement_id is not None:
        requirement = (
            await db.execute(
                select(Requirement).where(
                    Requirement.id == requirement_id,
                    Requirement.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if requirement is None:
            raise HTTPException(status_code=422, detail="Linked requirement does not belong to the selected project")

    if test_case_id is not None:
        test_case = (
            await db.execute(
                select(TestCase).where(
                    TestCase.id == test_case_id,
                    TestCase.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if test_case is None:
            raise HTTPException(status_code=422, detail="Linked test case does not belong to the selected project")


async def create_test_data(db: AsyncSession, project_id: int, body: TestDataCreate, user_id: int) -> TestData:
    template = None
    if body.template_id is not None:
        template = await get_template(db, body.template_id)
        if template is None or template.project_id != project_id:
            raise HTTPException(status_code=404, detail="Test data template not found")
    await _validate_project_links(db, project_id, body.requirement_id, body.test_case_id)

    item = TestData(
        project_id=project_id,
        created_by=user_id,
        updated_by=user_id,
        test_case_id=body.test_case_id,
        requirement_id=body.requirement_id,
        execution_run_id=body.execution_run_id,
        template_id=body.template_id,
        data_id=temporary_id("TD"),
        name=body.name,
        description=body.description,
        data_type=body.data_type,
        source_type=body.source_type,
        status="pending_approval" if body.submit_for_approval else "draft",
        approval_status="pending_approval" if body.submit_for_approval else "draft",
        telecom_domain=body.telecom_domain,
        test_phase=body.test_phase,
        product_group=body.product_group,
        product=body.product,
        sub_request_type=body.sub_request_type,
        environment=body.environment,
        version=body.version,
        tags=body.tags,
        linked_requirement_key=body.linked_requirement_key,
        linked_jira_issue_key=body.linked_jira_issue_key,
        linked_jira_url=body.linked_jira_url,
        linked_defect_id=body.linked_defect_id,
        data_payload_json=_normalize_payload(body.data_payload_json),
        schema_json=body.schema_json or (template.schema_json if template else None),
        sample_preview_json=body.sample_preview_json,
        sensitive_fields_json=body.sensitive_fields_json,
        masking_rules_json=body.masking_rules_json or (template.masking_rules_json if template else None),
        validation_rules_json=body.validation_rules_json or (template.validation_rules_json if template else None),
        privacy_level=body.privacy_level,
        contains_pii=body.contains_pii,
        notes=body.notes,
        masking_status="pending" if body.contains_pii else "not_required",
        synthetic_generation_status="not_required",
        generation_status="not_requested",
        actual_record_count=1,
        validation_status="not_validated",
        reservation_status="available",
    )
    db.add(item)
    await db.flush()
    item.data_id = display_id("TD", item.id)
    item.sample_preview_json = _preview_payload(item.data_payload_json or {}, _as_list(item.sensitive_fields_json))
    await db.flush()

    score, quality_status, issues = _quality_check(item)
    item.quality_score = score
    item.quality_status = quality_status
    item.quality_issues_json = issues
    await db.flush()

    parents: list[tuple[str, int]] = []
    if item.requirement_id:
        parents.append(("requirement", item.requirement_id))
    if item.test_case_id:
        parents.append(("test_case", item.test_case_id))
    if parents:
        await traceability_service.create_lineage_many(
            db,
            project_id=project_id,
            parents=parents,
            child_type="test_data",
            child_id=item.id,
            agent_run_id=item.agent_run_id,
            metadata={"source_type": item.source_type},
        )
    return item


async def update_test_data(db: AsyncSession, item: TestData, body: TestDataUpdate, user_id: int) -> TestData:
    updates = body.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        _ensure_allowed_status_transition(item.status, updates["status"])
    await _validate_project_links(
        db,
        item.project_id,
        updates.get("requirement_id", item.requirement_id),
        updates.get("test_case_id", item.test_case_id),
    )
    for key, value in updates.items():
        setattr(item, key, value)
    item.updated_by = user_id
    if "data_payload_json" in updates:
        item.sample_preview_json = _preview_payload(item.data_payload_json or {}, _as_list(item.sensitive_fields_json))
    score, quality_status, issues = _quality_check(item)
    item.quality_score = score
    item.quality_status = quality_status
    item.quality_issues_json = issues
    await db.flush()
    return item


async def delete_test_data(db: AsyncSession, item: TestData) -> None:
    item.status = "archived"
    item.approval_status = "rejected" if item.approval_status == "draft" else item.approval_status
    await db.flush()


async def validate_test_data(db: AsyncSession, item: TestData) -> TestData:
    score, quality_status, issues = _quality_check(item)
    item.quality_score = score
    item.quality_status = quality_status
    item.quality_issues_json = issues
    item.validation_status = quality_status if quality_status in {"valid", "warning", "invalid"} else "not_validated"
    item.validation_summary_json = {"issue_count": len(issues)}
    if quality_status == "invalid" and item.status == "active":
        item.status = "invalid"
    await db.flush()
    return item


async def mask_test_data(db: AsyncSession, item: TestData, body: TestDataMaskRequest, user_id: int) -> TestData:
    payload = _normalize_payload(item.data_payload_json)
    fields = body.fields or _as_list(item.sensitive_fields_json)
    if item.contains_pii and not fields:
        raise HTTPException(status_code=422, detail="No sensitive fields available to mask")
    item.data_payload_json = _mask_payload(payload, [str(field) for field in fields], body.keep_last)
    item.sample_preview_json = _preview_payload(item.data_payload_json, [str(field) for field in fields])
    item.sensitive_fields_json = [str(field) for field in fields]
    item.masking_status = "masked"
    item.updated_by = user_id
    await validate_test_data(db, item)
    return item


async def reserve_test_data(
    db: AsyncSession,
    item: TestData,
    *,
    user_id: int,
    reserved_for_execution_id: int | None,
    duration_minutes: int,
) -> TestData:
    if item.approval_status != "approved" and item.status not in {"approved", "active"}:
        raise HTTPException(status_code=409, detail="Only approved or active test data can be reserved")
    if item.quality_status == "invalid":
        raise HTTPException(status_code=409, detail="Invalid test data cannot be reserved")
    if item.reservation_status == "reserved" and item.reserved_by != user_id:
        if not item.reservation_expires_at or item.reservation_expires_at > now_utc():
            raise HTTPException(status_code=409, detail="Test data is already reserved")
    item.reservation_status = "reserved"
    item.status = "reserved"
    item.reserved_by = user_id
    item.reserved_for_execution_id = reserved_for_execution_id
    item.reserved_at = now_utc()
    item.released_at = None
    item.reservation_expires_at = now_utc() + timedelta(minutes=max(1, duration_minutes))
    await db.flush()
    return item


async def release_test_data(db: AsyncSession, item: TestData, user_id: int) -> TestData:
    if item.reservation_status != "reserved":
        raise HTTPException(status_code=409, detail="Test data is not reserved")
    if item.reserved_by not in {None, user_id}:
        raise HTTPException(status_code=403, detail="You cannot release another user's reservation")
    item.reservation_status = "released"
    item.status = "active" if item.approval_status == "approved" else item.status
    item.released_at = now_utc()
    item.reserved_by = None
    item.reserved_for_execution_id = None
    item.reservation_expires_at = None
    await db.flush()
    return item


async def consume_test_data(db: AsyncSession, item: TestData, user_id: int) -> TestData:
    if item.reservation_status not in {"reserved", "available", "released"}:
        raise HTTPException(status_code=409, detail="Test data cannot be consumed in its current state")
    if item.reservation_status == "reserved" and item.reserved_by not in {None, user_id}:
        raise HTTPException(status_code=403, detail="Reserved test data belongs to another user")
    item.reservation_status = "consumed"
    item.status = "consumed"
    item.consumed_at = now_utc()
    item.last_used_at = item.consumed_at
    item.usage_count = (item.usage_count or 0) + 1
    await db.flush()
    return item


async def submit_test_data(db: AsyncSession, item: TestData, user_id: int, notes: str | None = None) -> TestData:
    item.status = "pending_approval"
    item.approval_status = "pending_approval"
    item.updated_by = user_id
    item.rejection_reason = None
    await db.flush()
    if notes:
        item.metadata_ = {**(item.metadata_ or {}), "submission_notes": notes}
        await db.flush()
    return item


async def approve_test_data(db: AsyncSession, item: TestData, user_id: int, notes: str | None = None) -> TestData:
    item.status = "approved"
    item.approval_status = "approved"
    item.approved_by = user_id
    item.approved_at = now_utc()
    item.updated_by = user_id
    if item.reservation_status in {"released", "expired"}:
        item.reservation_status = "available"
    elif item.reservation_status == "available":
        item.status = "active"
    await approval_service.create_approval_action(
        db,
        project_id=item.project_id,
        user_id=user_id,
        entity_type="test_data",
        entity_id=item.id,
        action="approve",
        notes=notes,
        old_value={"status": "pending_approval"},
        new_value={"status": item.status, "approval_status": item.approval_status},
        jira_issue_key=item.linked_jira_issue_key,
        agent_run_id=item.agent_run_id,
    )
    await db.flush()
    return item


async def reject_test_data(db: AsyncSession, item: TestData, user_id: int, notes: str | None = None) -> TestData:
    item.status = "rejected"
    item.approval_status = "rejected"
    item.rejection_reason = notes
    item.updated_by = user_id
    await approval_service.create_approval_action(
        db,
        project_id=item.project_id,
        user_id=user_id,
        entity_type="test_data",
        entity_id=item.id,
        action="reject",
        notes=notes,
        old_value={"status": "pending_approval"},
        new_value={"status": item.status, "approval_status": item.approval_status},
        jira_issue_key=item.linked_jira_issue_key,
        agent_run_id=item.agent_run_id,
    )
    await db.flush()
    return item


async def test_data_history(db: AsyncSession, item_id: int) -> list[ApprovalAction]:
    stmt = (
        select(ApprovalAction)
        .where(ApprovalAction.entity_type == "test_data", ApprovalAction.entity_id == item_id)
        .order_by(ApprovalAction.created_at.desc())
    )
    return list((await db.execute(stmt)).scalars().all())


async def test_data_summary(db: AsyncSession, project_id: int) -> dict[str, Any]:
    items = list((await db.execute(select(TestData).where(TestData.project_id == project_id))).scalars().all())
    by_status: dict[str, int] = {}
    by_source_type: dict[str, int] = {}
    by_reservation_status: dict[str, int] = {}
    by_quality_status: dict[str, int] = {}
    for item in items:
        by_status[item.status] = by_status.get(item.status, 0) + 1
        by_source_type[item.source_type] = by_source_type.get(item.source_type, 0) + 1
        by_reservation_status[item.reservation_status] = by_reservation_status.get(item.reservation_status, 0) + 1
        by_quality_status[item.quality_status] = by_quality_status.get(item.quality_status, 0) + 1

    linked_test_cases = sum(1 for item in items if item.test_case_id is not None)
    return {
        "total_data_sets": len(items),
        "approved": sum(1 for item in items if item.approval_status == "approved"),
        "pending_approval": sum(1 for item in items if item.approval_status == "pending_approval"),
        "synthetic": sum(1 for item in items if item.source_type in {"synthetic", "ai_generated"}),
        "masked": sum(1 for item in items if item.masking_status == "masked"),
        "reserved": sum(1 for item in items if item.reservation_status == "reserved"),
        "expired": sum(1 for item in items if item.status == "expired" or item.reservation_status == "expired"),
        "linked_test_cases": linked_test_cases,
        "data_quality_issues": sum(1 for item in items if item.quality_status in {"warning", "invalid"}),
        "by_status": by_status,
        "by_source_type": by_source_type,
        "by_reservation_status": by_reservation_status,
        "by_quality_status": by_quality_status,
    }


async def list_templates(db: AsyncSession, project_id: int) -> list[TestDataTemplate]:
    stmt = select(TestDataTemplate).where(TestDataTemplate.project_id == project_id).order_by(TestDataTemplate.updated_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def create_template(db: AsyncSession, project_id: int, body: TestDataTemplateCreate, user_id: int) -> TestDataTemplate:
    template = TestDataTemplate(
        project_id=project_id,
        created_by=user_id,
        updated_by=user_id,
        template_id=temporary_id("TDT"),
        **body.model_dump(),
    )
    db.add(template)
    await db.flush()
    template.template_id = display_id("TDT", template.id)
    await db.flush()
    return template


async def update_template(db: AsyncSession, template: TestDataTemplate, body: TestDataTemplateUpdate, user_id: int) -> TestDataTemplate:
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(template, key, value)
    template.updated_by = user_id
    await db.flush()
    return template


async def delete_template(db: AsyncSession, template: TestDataTemplate) -> None:
    await db.delete(template)
    await db.flush()


async def linked_test_case_count(db: AsyncSession, item: TestData) -> int:
    if item.test_case_id is None:
        return 0
    return int((await db.execute(select(func.count()).select_from(TestCase).where(TestCase.id == item.test_case_id))).scalar_one())
