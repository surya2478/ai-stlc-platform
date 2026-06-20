"""Workflow for external-tool test data generation requests."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.approval import ApprovalAction
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_data import TestData, TestDataRecord
from app.schemas.test_data import TestDataGenerateRequest
from app.services.display_id_service import display_id, temporary_id
from app.services.external_test_data_tools import get_external_test_data_tool_client


def _utc_datetime_for_date(value):
    if value is None:
        return None
    return datetime.combine(value, datetime.min.time(), tzinfo=timezone.utc)


async def _validate_project_links(db: AsyncSession, project_id: int, linked_requirement_id: int | None, linked_test_case_id: int | None) -> None:
    if linked_requirement_id is not None:
        requirement = (
            await db.execute(
                select(Requirement).where(
                    Requirement.id == linked_requirement_id,
                    Requirement.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if requirement is None:
            raise HTTPException(status_code=422, detail="Linked requirement does not belong to the selected project")

    if linked_test_case_id is not None:
        test_case = (
            await db.execute(
                select(TestCase).where(
                    TestCase.id == linked_test_case_id,
                    TestCase.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if test_case is None:
            raise HTTPException(status_code=422, detail="Linked test case does not belong to the selected project")


async def create_external_generation_request(
    db: AsyncSession,
    project_id: int,
    request: TestDataGenerateRequest,
    current_user,
) -> TestData:
    await _validate_project_links(db, project_id, request.linked_requirement_id, request.linked_test_case_id)

    client = get_external_test_data_tool_client(request.external_tool)
    result = await client.create_generation_request(request.model_dump(mode="json"))

    item = TestData(
        project_id=project_id,
        created_by=current_user.id,
        updated_by=current_user.id,
        requirement_id=request.linked_requirement_id,
        test_case_id=request.linked_test_case_id,
        data_id=temporary_id("TD"),
        name=request.name,
        data_type=request.data_type,
        source_type="external_tool",
        status="draft" if result.generation_status == "generated" else "pending_generation",
        approval_status="draft",
        telecom_domain=request.telecom_domain,
        test_phase=request.test_phase,
        product_group=request.product_group,
        product=request.product,
        sub_request_type=request.sub_request_type,
        environment=request.environment,
        contains_pii=False,
        privacy_level="internal",
        masking_status="not_required",
        synthetic_generation_status="not_required",
        generation_status=result.generation_status,
        generation_mode=request.generation_mode,
        requested_record_count=request.number_of_records,
        actual_record_count=len(result.generated_records),
        external_tool=request.external_tool,
        external_suite_id=request.external_suite_id,
        external_dataset_id=request.external_dataset_id,
        external_url=str(request.external_url) if request.external_url else None,
        request_notes=request.request_notes,
        priority=request.priority,
        expected_by_date=_utc_datetime_for_date(request.expected_by_date),
        validation_status="not_validated",
        validation_summary_json={"integration_status": result.integration_status},
        sample_preview_json=result.generated_records[0] if result.generated_records else None,
        data_payload_json=result.generated_records[0] if result.generated_records else {},
        reservation_status="available",
    )
    db.add(item)
    await db.flush()
    item.data_id = display_id("TD", item.id)

    for index, row in enumerate(result.generated_records, start=1):
        db.add(
            TestDataRecord(
                data_set_id=item.id,
                project_id=project_id,
                row_number=index,
                record_key=f"{item.data_id}-R{index:04d}",
                payload_json=row,
                masked_payload_json=None,
                validation_status="valid",
                validation_errors_json=[],
            )
        )

    db.add(
        ApprovalAction(
            project_id=project_id,
            user_id=current_user.id,
            action_type="request_test_data_generation",
            entity_type="test_data",
            entity_id=item.id,
            decision="requested",
            notes=request.request_notes,
            source="platform",
            actor_role=current_user.role,
            old_value=None,
            new_value={
                "generation_status": item.generation_status,
                "external_tool": item.external_tool,
                "requested_record_count": item.requested_record_count,
            },
        )
    )
    await db.flush()
    return item
