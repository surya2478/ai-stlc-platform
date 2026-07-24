"""Pydantic schemas for the test case CSV/XLSX import preview/confirm flow."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class TestCaseImportPreviewResponse(BaseModel):
    preview_token: str
    filename: str
    file_type: str
    detected_columns: list[str]
    row_count: int
    preview_rows: list[dict[str, Any]]
    validation_errors: list[dict[str, Any]]
    validation_warnings: list[dict[str, Any]]
    can_import: bool


class TestCaseImportConfirmRequest(BaseModel):
    preview_token: str


class TestCaseImportConfirmResponse(BaseModel):
    imported_count: int
    skipped_count: int
    created_test_case_ids: list[int]
    validation_summary: dict[str, Any]
