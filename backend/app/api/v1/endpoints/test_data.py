"""Test Data Management endpoints."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile

from app.api.deps import CurrentUser, DBSession, require_entity_project_access, require_permission, require_project_access
from app.models.test_data import TestData
from app.schemas.common import MessageResponse
from app.schemas.test_data import (
    TestDataApprovalRequest,
    TestDataCreate,
    TestDataGenerateResponse,
    TestDataGenerateRequest,
    TestDataHistoryOut,
    TestDataImportConfirmRequest,
    TestDataImportConfirmResponse,
    TestDataImportMetadata,
    TestDataImportPreviewResponse,
    TestDataMaskRequest,
    TestDataOut,
    TestDataReservationRequest,
    TestDataSummaryOut,
    TestDataTemplateCreate,
    TestDataTemplateOut,
    TestDataTemplateUpdate,
    TestDataUpdate,
    TestDataValidateOut,
)
from app.services import test_data_generation_service, test_data_import_service, test_data_service
from app.services.rbac_service import (
    APPROVE_TEST_DATA,
    CREATE_TEST_DATA,
    DELETE_TEST_DATA,
    EDIT_TEST_DATA,
    GENERATE_TEST_DATA,
    IMPORT_TEST_DATA,
    MASK_TEST_DATA,
    RESERVE_TEST_DATA,
    VIEW_SENSITIVE_TEST_DATA,
    VIEW_TEST_DATA,
    user_has_permission,
)

router = APIRouter()


async def _serialize_item(db, current_user, item: TestData) -> TestDataOut:
    can_view_sensitive = await user_has_permission(db, current_user, item.project_id, VIEW_SENSITIVE_TEST_DATA)
    payload = item.data_payload_json if can_view_sensitive else item.sample_preview_json
    return TestDataOut(
        id=item.id,
        project_id=item.project_id,
        data_id=item.data_id,
        name=item.name,
        description=item.description,
        data_type=item.data_type,
        source_type=item.source_type,
        status=item.status,
        approval_status=item.approval_status,
        telecom_domain=item.telecom_domain,
        test_phase=item.test_phase,
        product_group=item.product_group,
        product=item.product,
        sub_request_type=item.sub_request_type,
        environment=item.environment,
        version=item.version,
        tags=item.tags,
        template_id=item.template_id,
        linked_requirement_id=item.linked_requirement_id,
        linked_requirement_key=item.linked_requirement_key,
        linked_test_case_id=item.linked_test_case_id,
        linked_execution_run_id=item.linked_execution_run_id,
        linked_jira_issue_key=item.linked_jira_issue_key,
        linked_jira_url=item.linked_jira_url,
        linked_defect_id=item.linked_defect_id,
        data_payload_json=payload,
        sample_preview_json=item.sample_preview_json,
        sensitive_fields_json=item.sensitive_fields_json,
        privacy_level=item.privacy_level,
        contains_pii=item.contains_pii,
        masking_status=item.masking_status,
        synthetic_generation_status=item.synthetic_generation_status,
        generation_status=item.generation_status,
        generation_mode=item.generation_mode,
        requested_record_count=item.requested_record_count,
        actual_record_count=item.actual_record_count,
        external_tool=item.external_tool,
        external_suite_id=item.external_suite_id,
        external_dataset_id=item.external_dataset_id,
        external_url=item.external_url,
        request_notes=item.request_notes,
        priority=item.priority,
        expected_by_date=item.expected_by_date,
        validation_status=item.validation_status,
        validation_summary_json=item.validation_summary_json,
        import_filename=item.import_filename,
        reservation_status=item.reservation_status,
        reserved_by=item.reserved_by,
        reserved_for_execution_id=item.reserved_for_execution_id,
        reservation_expires_at=item.reservation_expires_at,
        consumed_at=item.consumed_at,
        quality_score=item.quality_score,
        quality_status=item.quality_status,
        quality_issues_json=item.quality_issues_json,
        jira_sync_status=item.jira_sync_status,
        last_synced_at=item.last_synced_at,
        sync_error=item.sync_error,
        created_by=item.created_by,
        updated_by=item.updated_by,
        approved_by=item.approved_by,
        approved_at=item.approved_at,
        last_used_at=item.last_used_at,
        usage_count=item.usage_count,
        agent_run_id=item.agent_run_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/projects/{project_id}", response_model=list[TestDataOut])
async def list_project_test_data(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    status: str | None = Query(None),
    source_type: str | None = Query(None),
    reservation_status: str | None = Query(None),
):
    await require_permission(VIEW_TEST_DATA, project_id, current_user, db)
    items = await test_data_service.list_test_data(
        db,
        project_id,
        status=status,
        source_type=source_type,
        reservation_status=reservation_status,
    )
    return [await _serialize_item(db, current_user, item) for item in items]


@router.get("/projects/{project_id}/summary", response_model=TestDataSummaryOut)
async def get_project_test_data_summary(project_id: int, db: DBSession, current_user: CurrentUser):
    await require_permission(VIEW_TEST_DATA, project_id, current_user, db)
    return await test_data_service.test_data_summary(db, project_id)


@router.get("/{data_id}", response_model=TestDataOut)
async def get_test_data_item(data_id: int, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(VIEW_TEST_DATA, item.project_id, current_user, db)
    return await _serialize_item(db, current_user, item)


@router.post("/projects/{project_id}", response_model=TestDataOut, status_code=201)
async def create_test_data_item(project_id: int, body: TestDataCreate, db: DBSession, current_user: CurrentUser):
    await require_permission(CREATE_TEST_DATA, project_id, current_user, db)
    item = await test_data_service.create_test_data(db, project_id, body, current_user.id)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.patch("/{data_id}", response_model=TestDataOut)
async def update_test_data_item(data_id: int, body: TestDataUpdate, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(EDIT_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.update_test_data(db, item, body, current_user.id)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.delete("/{data_id}", response_model=MessageResponse)
async def delete_test_data_item(data_id: int, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(DELETE_TEST_DATA, item.project_id, current_user, db)
    await test_data_service.delete_test_data(db, item)
    await db.commit()
    return MessageResponse(message="Test data archived")


@router.post("/projects/{project_id}/generate", response_model=TestDataGenerateResponse, status_code=202)
async def generate_test_data(project_id: int, body: TestDataGenerateRequest, db: DBSession, current_user: CurrentUser):
    await require_permission(GENERATE_TEST_DATA, project_id, current_user, db)
    item = await test_data_generation_service.create_external_generation_request(db, project_id, body, current_user)
    await db.commit()
    await db.refresh(item)
    return TestDataGenerateResponse(
        data_set_id=item.id,
        data_id=item.data_id,
        generation_status=item.generation_status,
        status=item.status,
        external_tool=item.external_tool,
        message="External generation request saved successfully.",
    )


@router.post("/projects/{project_id}/import/preview", response_model=TestDataImportPreviewResponse, status_code=201)
async def preview_test_data_import(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    file: UploadFile = File(...),
    name: str | None = Form(None),
    data_type: str = Form(...),
    telecom_domain: str = Form(...),
    test_phase: str = Form(...),
    environment: str = Form(...),
    contains_pii: bool = Form(False),
    privacy_level: str = Form("internal"),
    linked_requirement_id: int | None = Form(None),
    linked_test_case_id: int | None = Form(None),
    import_mode: str = Form("create_new_dataset"),
    existing_data_set_id: int | None = Form(None),
    validate_before_import: bool = Form(True),
):
    await require_permission(IMPORT_TEST_DATA, project_id, current_user, db)
    metadata = TestDataImportMetadata(
        name=name,
        data_type=data_type,
        telecom_domain=telecom_domain,
        test_phase=test_phase,
        environment=environment,
        contains_pii=contains_pii,
        privacy_level=privacy_level,
        linked_requirement_id=linked_requirement_id,
        linked_test_case_id=linked_test_case_id,
        import_mode=import_mode,
        existing_data_set_id=existing_data_set_id,
        validate_before_import=validate_before_import,
    )
    preview = await test_data_import_service.create_import_preview(db, project_id, current_user.id, file, metadata)
    await db.commit()
    return TestDataImportPreviewResponse(
        preview_token=preview.preview_token,
        filename=preview.filename,
        file_type=preview.file_type,
        detected_columns=list(preview.detected_columns_json or []),
        row_count=preview.row_count,
        preview_rows=list(preview.parsed_rows_json or [])[:10],
        validation_errors=list(preview.validation_errors_json or []),
        validation_warnings=list(preview.validation_warnings_json or []),
        can_import=preview.can_import,
    )


@router.post("/projects/{project_id}/import/confirm", response_model=TestDataImportConfirmResponse, status_code=201)
async def confirm_test_data_import(
    project_id: int,
    body: TestDataImportConfirmRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    await require_permission(IMPORT_TEST_DATA, project_id, current_user, db)
    item, imported_count, skipped_count = await test_data_import_service.confirm_import(db, project_id, current_user, body.preview_token)
    await db.commit()
    await db.refresh(item)
    return TestDataImportConfirmResponse(
        data_set_id=item.id,
        data_id=item.data_id,
        imported_record_count=imported_count,
        skipped_record_count=skipped_count,
        validation_summary=item.validation_summary_json or {},
    )


@router.post("/{data_id}/validate", response_model=TestDataValidateOut)
async def validate_test_data_item(data_id: int, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(VIEW_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.validate_test_data(db, item)
    await db.commit()
    return TestDataValidateOut(
        data_id=item.id,
        quality_score=item.quality_score or 0,
        quality_status=item.quality_status,
        quality_issues_json=item.quality_issues_json or [],
    )


@router.post("/{data_id}/mask", response_model=TestDataOut)
async def mask_test_data_item(data_id: int, body: TestDataMaskRequest, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(MASK_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.mask_test_data(db, item, body, current_user.id)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.post("/{data_id}/reserve", response_model=TestDataOut)
async def reserve_test_data_item(data_id: int, body: TestDataReservationRequest, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(RESERVE_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.reserve_test_data(
        db,
        item,
        user_id=current_user.id,
        reserved_for_execution_id=body.reserved_for_execution_id,
        duration_minutes=body.duration_minutes,
    )
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.post("/{data_id}/release", response_model=TestDataOut)
async def release_test_data_item(data_id: int, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(RESERVE_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.release_test_data(db, item, current_user.id)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.post("/{data_id}/consume", response_model=TestDataOut)
async def consume_test_data_item(data_id: int, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(RESERVE_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.consume_test_data(db, item, current_user.id)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.post("/{data_id}/submit", response_model=TestDataOut)
async def submit_test_data_item(data_id: int, body: TestDataApprovalRequest, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(EDIT_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.submit_test_data(db, item, current_user.id, body.notes)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.post("/{data_id}/approve", response_model=TestDataOut)
async def approve_test_data_item(data_id: int, body: TestDataApprovalRequest, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(APPROVE_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.approve_test_data(db, item, current_user.id, body.notes)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.post("/{data_id}/reject", response_model=TestDataOut)
async def reject_test_data_item(data_id: int, body: TestDataApprovalRequest, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(APPROVE_TEST_DATA, item.project_id, current_user, db)
    item = await test_data_service.reject_test_data(db, item, current_user.id, body.notes)
    await db.commit()
    await db.refresh(item)
    return await _serialize_item(db, current_user, item)


@router.get("/{data_id}/history", response_model=list[TestDataHistoryOut])
async def get_test_data_item_history(data_id: int, db: DBSession, current_user: CurrentUser):
    item = await test_data_service.get_test_data(db, data_id)
    if not item:
        raise HTTPException(status_code=404, detail="Test data not found")
    await require_permission(VIEW_TEST_DATA, item.project_id, current_user, db)
    return await test_data_service.test_data_history(db, data_id)


@router.get("/templates/projects/{project_id}", response_model=list[TestDataTemplateOut])
async def list_test_data_templates(project_id: int, db: DBSession, current_user: CurrentUser):
    await require_permission(VIEW_TEST_DATA, project_id, current_user, db)
    return await test_data_service.list_templates(db, project_id)


@router.post("/templates/projects/{project_id}", response_model=TestDataTemplateOut, status_code=201)
async def create_test_data_template(project_id: int, body: TestDataTemplateCreate, db: DBSession, current_user: CurrentUser):
    await require_permission(CREATE_TEST_DATA, project_id, current_user, db)
    template = await test_data_service.create_template(db, project_id, body, current_user.id)
    await db.commit()
    await db.refresh(template)
    return template


@router.patch("/templates/{template_id}", response_model=TestDataTemplateOut)
async def update_test_data_template(template_id: int, body: TestDataTemplateUpdate, db: DBSession, current_user: CurrentUser):
    template = await test_data_service.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Test data template not found")
    await require_permission(EDIT_TEST_DATA, template.project_id, current_user, db)
    template = await test_data_service.update_template(db, template, body, current_user.id)
    await db.commit()
    await db.refresh(template)
    return template


@router.delete("/templates/{template_id}", response_model=MessageResponse)
async def delete_test_data_template(template_id: int, db: DBSession, current_user: CurrentUser):
    template = await test_data_service.get_template(db, template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Test data template not found")
    await require_permission(DELETE_TEST_DATA, template.project_id, current_user, db)
    await test_data_service.delete_template(db, template)
    await db.commit()
    return MessageResponse(message="Test data template deleted")
