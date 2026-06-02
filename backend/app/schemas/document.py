"""Pydantic schemas for uploaded documents."""
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class DocumentBase(BaseModel):
    original_filename: str
    file_type: str
    file_size_bytes: int


class DocumentOut(DocumentBase):
    id: int
    project_id: int
    stored_filename: str
    status: str
    page_count: int | None = None
    extracted_text: str | None = None
    metadata_: dict[str, Any] | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DocumentListOut(BaseModel):
    id: int
    project_id: int
    original_filename: str
    file_type: str
    file_size_bytes: int
    status: str
    page_count: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}
