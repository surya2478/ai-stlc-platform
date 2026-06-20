"""CSV/Excel preview and confirm workflow for test data imports."""
from __future__ import annotations

import csv
import io
import uuid
from datetime import timedelta

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.approval import ApprovalAction
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.models.test_data import TestData, TestDataImportPreview, TestDataRecord
from app.schemas.test_data import TestDataImportMetadata
from app.services.display_id_service import display_id, temporary_id
from app.services.test_data_service import now_utc

settings = get_settings()
ALLOWED_IMPORT_EXTENSIONS = {".csv", ".xlsx", ".xls"}


def _validate_upload_basics(file: UploadFile) -> tuple[str, str]:
    filename = file.filename or "upload"
    suffix = f".{filename.rsplit('.', 1)[-1].lower()}" if "." in filename else ""
    if suffix not in ALLOWED_IMPORT_EXTENSIONS:
        raise HTTPException(status_code=415, detail="Only CSV and Excel files are supported")
    return filename, suffix


def _decode_csv(contents: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return contents.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=415, detail="CSV encoding is not supported")


def _parse_csv(contents: bytes) -> tuple[list[str], list[dict]]:
    decoded = _decode_csv(contents)
    reader = csv.DictReader(io.StringIO(decoded))
    headers = reader.fieldnames or []
    if not headers or any(header is None or not str(header).strip() for header in headers):
        raise HTTPException(status_code=422, detail="CSV file must include a non-empty header row")
    normalized_headers = [str(header).strip() for header in headers]
    if len(set(normalized_headers)) != len(normalized_headers):
        raise HTTPException(status_code=422, detail="CSV file contains duplicate headers")
    rows = [{key.strip(): value for key, value in row.items()} for row in reader]
    return normalized_headers, rows


def _parse_excel(contents: bytes) -> tuple[list[str], list[dict]]:
    import pandas as pd

    try:
        workbook = pd.ExcelFile(io.BytesIO(contents))
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Excel file could not be parsed") from exc

    if not workbook.sheet_names:
        raise HTTPException(status_code=422, detail="Excel file has no sheets")

    sheet = workbook.sheet_names[0]
    df = workbook.parse(sheet).fillna("")
    headers = [str(column).strip() for column in df.columns.tolist()]
    if not headers or any(not header for header in headers):
        raise HTTPException(status_code=422, detail="Excel file must include non-empty headers")
    if len(set(headers)) != len(headers):
        raise HTTPException(status_code=422, detail="Excel file contains duplicate headers")
    rows = [{str(key).strip(): value for key, value in row.items()} for row in df.to_dict(orient="records")]
    return headers, rows


async def _validate_project_links(db: AsyncSession, project_id: int, metadata: TestDataImportMetadata) -> None:
    if metadata.linked_requirement_id is not None:
        requirement = (
            await db.execute(
                select(Requirement).where(
                    Requirement.id == metadata.linked_requirement_id,
                    Requirement.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if requirement is None:
            raise HTTPException(status_code=422, detail="Linked requirement does not belong to the selected project")

    if metadata.linked_test_case_id is not None:
        test_case = (
            await db.execute(
                select(TestCase).where(
                    TestCase.id == metadata.linked_test_case_id,
                    TestCase.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if test_case is None:
            raise HTTPException(status_code=422, detail="Linked test case does not belong to the selected project")

    if metadata.import_mode == "append_to_existing_dataset":
        existing = (
            await db.execute(
                select(TestData).where(
                    TestData.id == metadata.existing_data_set_id,
                    TestData.project_id == project_id,
                )
            )
        ).scalar_one_or_none()
        if existing is None:
            raise HTTPException(status_code=422, detail="Existing data set does not belong to the selected project")


def _validate_rows(headers: list[str], rows: list[dict], metadata: TestDataImportMetadata) -> tuple[list[dict], list[dict]]:
    warnings: list[dict] = []
    errors: list[dict] = []
    seen_signatures: set[str] = set()

    if not rows:
        raise HTTPException(status_code=422, detail="Import file has no data rows")

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            errors.append({"row_number": index, "message": "Row is not a valid object"})
            continue
        if not any(str(value).strip() for value in row.values()):
            warnings.append({"row_number": index, "message": "Row is empty and will be skipped"})
            continue
        signature = "|".join(str(row.get(header, "")) for header in headers)
        if signature in seen_signatures:
            warnings.append({"row_number": index, "message": "Duplicate row detected"})
        else:
            seen_signatures.add(signature)

    if metadata.contains_pii and metadata.privacy_level == "public":
        errors.append({"field": "privacy_level", "message": "Privacy level cannot be public when the file contains PII"})

    return errors, warnings


async def create_import_preview(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    file: UploadFile,
    metadata: TestDataImportMetadata,
) -> TestDataImportPreview:
    await _validate_project_links(db, project_id, metadata)
    filename, suffix = _validate_upload_basics(file)

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    if len(contents) > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    if suffix == ".csv":
        headers, rows = _parse_csv(contents)
        file_type = "csv"
    else:
        headers, rows = _parse_excel(contents)
        file_type = "xlsx"

    errors, warnings = _validate_rows(headers, rows, metadata)
    preview = TestDataImportPreview(
        preview_token=uuid.uuid4().hex,
        project_id=project_id,
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        detected_columns_json=headers,
        row_count=len(rows),
        metadata_json=metadata.model_dump(mode="json"),
        parsed_rows_json=rows,
        validation_errors_json=errors,
        validation_warnings_json=warnings,
        can_import=len(errors) == 0,
        expires_at=now_utc() + timedelta(minutes=15),
    )
    db.add(preview)
    await db.flush()
    return preview


async def get_active_preview(db: AsyncSession, project_id: int, user_id: int, preview_token: str) -> TestDataImportPreview:
    preview = (
        await db.execute(
            select(TestDataImportPreview).where(
                TestDataImportPreview.preview_token == preview_token,
                TestDataImportPreview.project_id == project_id,
                TestDataImportPreview.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if preview is None:
        raise HTTPException(status_code=404, detail="Import preview not found")
    if preview.consumed_at is not None:
        raise HTTPException(status_code=409, detail="Import preview has already been used")
    if preview.expires_at <= now_utc():
        raise HTTPException(status_code=410, detail="Import preview has expired")
    return preview


async def confirm_import(
    db: AsyncSession,
    project_id: int,
    user,
    preview_token: str,
) -> tuple[TestData, int, int]:
    preview = await get_active_preview(db, project_id, user.id, preview_token)
    metadata = TestDataImportMetadata.model_validate(preview.metadata_json)

    rows = list(preview.parsed_rows_json or [])
    valid_rows = []
    skipped = 0
    for row in rows:
        if not any(str(value).strip() for value in row.values()):
            skipped += 1
            continue
        valid_rows.append(row)

    if metadata.import_mode == "append_to_existing_dataset":
        data_set = (
            await db.execute(select(TestData).where(TestData.id == metadata.existing_data_set_id, TestData.project_id == project_id))
        ).scalar_one()
        data_set.updated_by = user.id
        data_set.actual_record_count = (data_set.actual_record_count or 0) + len(valid_rows)
        data_set.import_filename = preview.filename
        data_set.validation_status = "warning" if preview.validation_warnings_json else "valid"
        data_set.validation_summary_json = {
            "warnings": len(preview.validation_warnings_json or []),
            "errors": len(preview.validation_errors_json or []),
        }
    else:
        data_set = TestData(
            project_id=project_id,
            created_by=user.id,
            updated_by=user.id,
            requirement_id=metadata.linked_requirement_id,
            test_case_id=metadata.linked_test_case_id,
            data_id=temporary_id("TD"),
            name=(metadata.name or preview.filename.rsplit(".", 1)[0]).strip() or "Imported Test Data",
            data_type=metadata.data_type,
            source_type="imported",
            status="pending_approval" if metadata.privacy_level == "restricted" else "draft",
            approval_status="pending_approval" if metadata.privacy_level == "restricted" else "draft",
            telecom_domain=metadata.telecom_domain,
            test_phase=metadata.test_phase,
            product_group=metadata.product_group,
            product=metadata.product,
            sub_request_type=metadata.sub_request_type,
            environment=metadata.environment,
            contains_pii=metadata.contains_pii,
            privacy_level=metadata.privacy_level,
            masking_status="pending" if metadata.contains_pii else "not_required",
            synthetic_generation_status="not_required",
            generation_status="not_requested",
            requested_record_count=len(valid_rows),
            actual_record_count=len(valid_rows),
            validation_status="warning" if preview.validation_warnings_json else "valid",
            validation_summary_json={
                "warnings": len(preview.validation_warnings_json or []),
                "errors": len(preview.validation_errors_json or []),
            },
            import_filename=preview.filename,
            sample_preview_json=valid_rows[0] if valid_rows else None,
            data_payload_json=valid_rows[0] if valid_rows else {},
            reservation_status="available",
        )
        db.add(data_set)
        await db.flush()
        data_set.data_id = display_id("TD", data_set.id)

    base_row_number = 0
    if metadata.import_mode == "append_to_existing_dataset":
        base_row_number = int(
            (
                await db.execute(
                    select(TestDataRecord.row_number)
                    .where(TestDataRecord.data_set_id == data_set.id)
                    .order_by(TestDataRecord.row_number.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            or 0
        )

    for offset, row in enumerate(valid_rows, start=1):
        db.add(
            TestDataRecord(
                data_set_id=data_set.id,
                project_id=project_id,
                row_number=base_row_number + offset,
                record_key=f"{data_set.data_id}-R{base_row_number + offset:04d}",
                payload_json=row,
                masked_payload_json=None,
                validation_status="valid",
                validation_errors_json=[],
            )
        )

    preview.consumed_at = now_utc()
    db.add(
        ApprovalAction(
            project_id=project_id,
            user_id=user.id,
            action_type="import_test_data",
            entity_type="test_data",
            entity_id=data_set.id,
            decision="imported",
            notes=f"Imported {len(valid_rows)} records from {preview.filename}",
            source="platform",
            actor_role=user.role,
            old_value=None,
            new_value={"record_count": len(valid_rows), "filename": preview.filename},
        )
    )
    await db.flush()
    return data_set, len(valid_rows), skipped
