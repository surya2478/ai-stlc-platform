"""CSV/Excel preview and confirm workflow for test case imports.

Accepts the UAT template's 22-column format (docs/autonomous-automation-lab/
test-case_template.xlsx). Modeled directly on test_data_import_service.py:
same preview-token / 15-minute-expiry / single-use pattern.

Column ownership follows the implementation plan's confirmed field
boundaries — plan-time fields (Environment, Planned Execution Sequence) and
execution-time fields (Tested By, Overall Status, Blocking Snag ID / Other
Reason, SIT) don't live on TestCase, so those columns are accepted in the
file (for round-trip compatibility with the template) but not persisted;
each produces a per-row warning explaining where to set them instead.
"""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.approval import ApprovalAction
from app.models.test_case import TestCase, TestCaseImportPreview
from app.services.display_id_service import display_id, temporary_id
from app.services.taxonomy_resolver import TAXONOMY_MODEL_BY_FIELD, TaxonomyResolver
from app.services.test_data_service import now_utc

settings = get_settings()
ALLOWED_IMPORT_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Template header -> canonical field key. Matching is case-insensitive and
# tolerant of the "/" vs " / " header variants seen in the source workbook.
_HEADER_ALIASES: dict[str, str] = {
    "id": "id",
    "domain": "domain",
    "channel": "channel",
    "product": "product",
    "area of test": "area_of_test",
    "test case id": "test_case_id",
    "environment": "environment",
    "sub request type": "sub_request_type",
    "test case objective": "test_case_objective",
    "pre-requisites": "preconditions",
    "prerequisites": "preconditions",
    "test steps": "steps",
    "expected results": "expected_result",
    "atc test case": "atc_test_case",
    "test case type": "test_case_type",
    "test case complexity": "test_case_complexity",
    "tested by": "tested_by",
    "jira id or ppm": "jira_or_ppm",
    "overall status": "overall_status",
    "blocking snag id/other reason": "blocking_snag",
    "blocking snag id / other reason": "blocking_snag",
    "sit": "sit",
    "planned exec sequence": "planned_execution_sequence",
    "planned execution sequence": "planned_execution_sequence",
    "critical tc mapping": "is_critical",
}

# Columns accepted in the file but not stored on TestCase — surfaced as a
# per-row warning naming where they actually belong.
_UNPERSISTED_FIELD_NOTE = {
    "environment": "Environment is set per test-plan enrollment (Test Planning screen), not on the test case.",
    "tested_by": "Tested By is recorded per execution result (Execution screen), not on the test case.",
    "overall_status": "Overall Status is the execution outcome (Execution screen), not on the test case.",
    "blocking_snag": "Blocking Snag ID / Other Reason is recorded per execution result (Execution screen).",
    "sit": "SIT status is recorded per execution result (Execution screen), not on the test case.",
    "planned_execution_sequence": "Planned Execution Sequence is set per test-plan enrollment (Test Planning screen).",
}

_TRUE_VALUES = {"yes", "y", "true", "1"}


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


def _normalize_header(header: str) -> str:
    return re.sub(r"\s+", " ", header.strip()).lower()


def _map_headers(raw_headers: list[str]) -> dict[str, str]:
    """Return {raw_header: canonical_field_key} for headers we recognize."""
    mapping: dict[str, str] = {}
    for header in raw_headers:
        key = _HEADER_ALIASES.get(_normalize_header(header))
        if key:
            mapping[header] = key
    return mapping


def _parse_csv(contents: bytes) -> tuple[list[str], list[dict]]:
    decoded = _decode_csv(contents)
    reader = csv.DictReader(io.StringIO(decoded))
    headers = reader.fieldnames or []
    if not headers or any(header is None or not str(header).strip() for header in headers):
        raise HTTPException(status_code=422, detail="CSV file must include a non-empty header row")
    normalized_headers = [str(header).strip() for header in headers]
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
    rows = [{str(key).strip(): value for key, value in row.items()} for row in df.to_dict(orient="records")]
    return headers, rows


def _split_lines(value: Any) -> list[str]:
    if value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [line.strip() for line in re.split(r"[\n;]", text) if line.strip()]


def _parse_steps(value: Any) -> list[dict]:
    """Parse the export format ('1. action  ->  expected' per line) back into
    structured steps. A line with no separator becomes an action-only step."""
    lines = _split_lines(value)
    steps: list[dict] = []
    for i, raw_line in enumerate(lines, 1):
        line = re.sub(r"^\d+\.\s*", "", raw_line)
        parts = re.split(r"\s*(?:->|→)\s*", line, maxsplit=1)
        action = parts[0].strip()
        expected = parts[1].strip() if len(parts) > 1 else ""
        steps.append({"step_number": i, "action": action, "expected_result": expected})
    return steps


async def _resolve_row(
    resolver: TaxonomyResolver, mapped_row: dict[str, Any], row_number: int
) -> tuple[dict[str, Any], list[dict], list[dict]]:
    """Return (resolved_fields, errors, warnings) for one row."""
    errors: list[dict] = []
    warnings: list[dict] = []
    resolved: dict[str, Any] = {}

    test_case_id = str(mapped_row.get("test_case_id") or "").strip()
    objective = str(mapped_row.get("test_case_objective") or "").strip()
    if not test_case_id and not objective:
        errors.append({"row_number": row_number, "message": "Row needs a Test Case ID or Test Case Objective"})
        return resolved, errors, warnings

    resolved["test_case_id"] = test_case_id or None
    resolved["title"] = (objective[:500] if objective else test_case_id) or "Imported test case"
    resolved["test_case_objective"] = objective or None

    for field, model in TAXONOMY_MODEL_BY_FIELD.items():
        raw_value = str(mapped_row.get(field) or "").strip()
        if not raw_value:
            continue
        resolved_id = await resolver.resolve(model, raw_value)
        if resolved_id is not None:
            resolved[f"{field}_id"] = resolved_id
        else:
            warnings.append({
                "row_number": row_number,
                "message": f"'{raw_value}' does not match a known {field.replace('_', ' ')} — stored as free text",
            })
            resolved[f"{field}_legacy_text"] = raw_value

    preconditions = _split_lines(mapped_row.get("preconditions"))
    if preconditions:
        resolved["preconditions"] = preconditions

    steps = _parse_steps(mapped_row.get("steps"))
    if steps:
        resolved["steps"] = steps

    expected_result = str(mapped_row.get("expected_result") or "").strip()
    if expected_result:
        resolved["expected_result"] = expected_result

    atc = str(mapped_row.get("atc_test_case") or "").strip()
    if atc:
        resolved["atc_test_case"] = atc

    # The template collapses "JIRA ID or PPM" into one column with no reliable
    # way to tell them apart from the value alone (both commonly look like
    # "PROJECT-1234"). Rather than guess, store it as PPM ID — a real Jira
    # link should come from the explicit sync-jira flow, which pulls the
    # actual Jira issue rather than a value inferred from a spreadsheet cell.
    jira_or_ppm = str(mapped_row.get("jira_or_ppm") or "").strip()
    if jira_or_ppm:
        resolved["ppm_id"] = jira_or_ppm[:50]

    is_critical_raw = str(mapped_row.get("is_critical") or "").strip().lower()
    if is_critical_raw:
        resolved["is_critical"] = is_critical_raw in _TRUE_VALUES

    for field, note in _UNPERSISTED_FIELD_NOTE.items():
        if str(mapped_row.get(field) or "").strip():
            warnings.append({"row_number": row_number, "message": note})

    return resolved, errors, warnings


async def _check_duplicate_test_case_ids(
    db: AsyncSession, project_id: int, rows: list[dict]
) -> set[str]:
    ids = {r["test_case_id"] for r in rows if r.get("test_case_id")}
    if not ids:
        return set()
    result = await db.execute(
        select(TestCase.test_case_id).where(TestCase.project_id == project_id, TestCase.test_case_id.in_(ids))
    )
    return {row[0] for row in result.all()}


async def create_import_preview(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    file: UploadFile,
) -> TestCaseImportPreview:
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

    if not rows:
        raise HTTPException(status_code=422, detail="Import file has no data rows")

    header_map = _map_headers(headers)
    if not header_map:
        raise HTTPException(
            status_code=422,
            detail="No recognized UAT template columns found. Expected headers like "
                   "'Test Case ID', 'Test Case Objective', 'Test Steps', etc.",
        )

    resolver = TaxonomyResolver(db)
    resolved_rows: list[dict] = []
    all_errors: list[dict] = []
    all_warnings: list[dict] = []

    for index, row in enumerate(rows, start=1):
        if not any(str(value).strip() for value in row.values()):
            all_warnings.append({"row_number": index, "message": "Row is empty and will be skipped"})
            continue
        mapped_row = {field: row.get(raw_header) for raw_header, field in header_map.items()}
        resolved, errors, warnings = await _resolve_row(resolver, mapped_row, index)
        all_errors.extend(errors)
        all_warnings.extend(warnings)
        if not errors:
            resolved_rows.append(resolved)

    duplicates = await _check_duplicate_test_case_ids(db, project_id, resolved_rows)
    if duplicates:
        for row in resolved_rows:
            if row.get("test_case_id") in duplicates:
                all_errors.append({
                    "test_case_id": row["test_case_id"],
                    "message": f"Test Case ID '{row['test_case_id']}' already exists in this project",
                })
        resolved_rows = [r for r in resolved_rows if r.get("test_case_id") not in duplicates]

    preview = TestCaseImportPreview(
        preview_token=uuid.uuid4().hex,
        project_id=project_id,
        user_id=user_id,
        filename=filename,
        file_type=file_type,
        detected_columns_json=headers,
        row_count=len(rows),
        parsed_rows_json=rows,
        resolved_rows_json=resolved_rows,
        validation_errors_json=all_errors,
        validation_warnings_json=all_warnings,
        can_import=len(resolved_rows) > 0,
        expires_at=now_utc() + timedelta(minutes=15),
    )
    db.add(preview)
    await db.flush()
    return preview


async def get_active_preview(db: AsyncSession, project_id: int, user_id: int, preview_token: str) -> TestCaseImportPreview:
    preview = (
        await db.execute(
            select(TestCaseImportPreview).where(
                TestCaseImportPreview.preview_token == preview_token,
                TestCaseImportPreview.project_id == project_id,
                TestCaseImportPreview.user_id == user_id,
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
) -> tuple[list[int], int, int]:
    preview = await get_active_preview(db, project_id, user.id, preview_token)
    resolved_rows = list(preview.resolved_rows_json or [])
    if not resolved_rows:
        raise HTTPException(status_code=422, detail="No valid rows to import")

    # Re-check duplicates at confirm time in case rows were imported since preview.
    duplicates = await _check_duplicate_test_case_ids(db, project_id, resolved_rows)
    created_ids: list[int] = []
    skipped = 0

    for row in resolved_rows:
        if row.get("test_case_id") in duplicates:
            skipped += 1
            continue
        tc = TestCase(
            project_id=project_id,
            created_by=user.id,
            test_case_id=row.get("test_case_id") or temporary_id("TC"),
            title=row["title"],
            test_case_objective=row.get("test_case_objective"),
            preconditions=row.get("preconditions"),
            steps=row.get("steps"),
            expected_result=row.get("expected_result"),
            atc_test_case=row.get("atc_test_case"),
            ppm_id=row.get("ppm_id"),
            is_critical=row.get("is_critical", False),
            domain_id=row.get("domain_id"),
            channel_id=row.get("channel_id"),
            product_id=row.get("product_id"),
            area_of_test_id=row.get("area_of_test_id"),
            sub_request_type_id=row.get("sub_request_type_id"),
            test_case_type_id=row.get("test_case_type_id"),
            test_case_complexity_id=row.get("test_case_complexity_id"),
            telecom_domain=row.get("domain_legacy_text"),
            product=row.get("product_legacy_text"),
            sub_request_type=row.get("sub_request_type_legacy_text"),
            test_type=row.get("test_case_type_legacy_text"),
            status="draft",
        )
        db.add(tc)
        await db.flush()
        if not row.get("test_case_id"):
            tc.test_case_id = display_id("TC", tc.id)
        created_ids.append(tc.id)

    if not created_ids:
        raise HTTPException(status_code=409, detail="All rows were already imported since the preview was generated")

    preview.consumed_at = now_utc()
    db.add(
        ApprovalAction(
            project_id=project_id,
            user_id=user.id,
            action_type="import_test_cases",
            entity_type="test_case",
            entity_id=created_ids[0],
            decision="imported",
            notes=f"Imported {len(created_ids)} test cases from {preview.filename}",
            source="platform",
            actor_role=user.role,
            old_value=None,
            new_value={"count": len(created_ids), "filename": preview.filename},
        )
    )
    await db.flush()
    return created_ids, len(created_ids), skipped
