"""
Document Service
Handles file uploads, storage, and text extraction for PDF/DOCX/TXT/MD/CSV.
"""
import os
import uuid
from pathlib import Path

import aiofiles
from fastapi import UploadFile, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import get_settings
from app.models.document import UploadedDocument
from app.models.project import Project

settings = get_settings()

ALLOWED_TYPES = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
}

# Also match by extension for clients that send wrong MIME types
EXT_MAP = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".txt": "txt",
    ".md": "md",
    ".csv": "csv",
    ".xlsx": "xlsx",
}

MAX_SIZE = settings.max_upload_size_mb * 1024 * 1024


async def upload_document(
    db: AsyncSession,
    project_id: int,
    user_id: int,
    file: UploadFile,
) -> UploadedDocument:
    """Save file to disk, create DB record, then trigger async extraction."""

    # ── Determine file type ───────────────────────────────────────────────────
    ext = Path(file.filename or "").suffix.lower()
    file_type = ALLOWED_TYPES.get(file.content_type or "") or EXT_MAP.get(ext)
    if not file_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {file.content_type} / {ext}",
        )

    # ── Validate project exists ───────────────────────────────────────────────
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # ── Read and validate size ────────────────────────────────────────────────
    contents = await file.read()
    if len(contents) > MAX_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds {settings.max_upload_size_mb} MB limit",
        )

    # ── Store file ────────────────────────────────────────────────────────────
    storage_dir = Path(settings.file_storage_path) / "uploads" / str(project_id)
    storage_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{uuid.uuid4().hex}_{file.filename}"
    file_path = storage_dir / stored_name

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(contents)

    # ── DB record ─────────────────────────────────────────────────────────────
    doc = UploadedDocument(
        project_id=project_id,
        created_by=user_id,
        original_filename=file.filename or stored_name,
        stored_filename=stored_name,
        file_path=str(file_path),
        file_type=file_type,
        file_size_bytes=len(contents),
        status="uploaded",
    )
    db.add(doc)
    await db.flush()
    await db.refresh(doc)

    # ── Extract text synchronously (fast for small docs) ─────────────────────
    try:
        extracted, page_count = extract_text(str(file_path), file_type, contents)
        doc.extracted_text = extracted
        doc.page_count = page_count
        doc.status = "processed"
    except Exception as exc:
        doc.status = "failed"
        doc.metadata_ = {"extraction_error": str(exc)}

    await db.flush()
    await db.refresh(doc)
    return doc


def extract_text(file_path: str, file_type: str, contents: bytes) -> tuple[str, int | None]:
    """
    Extract plain text from a document.
    Returns (text, page_count).
    """
    if file_type == "pdf":
        return _extract_pdf(contents)
    elif file_type == "docx":
        return _extract_docx(contents)
    elif file_type in ("txt", "md"):
        return contents.decode("utf-8", errors="replace"), None
    elif file_type == "csv":
        return contents.decode("utf-8", errors="replace"), None
    elif file_type == "xlsx":
        return _extract_xlsx(contents)
    return "", None


def _extract_pdf(contents: bytes) -> tuple[str, int]:
    import fitz  # PyMuPDF
    import io
    doc = fitz.open(stream=contents, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text())
    return "\n\n".join(pages), len(doc)


def _extract_docx(contents: bytes) -> tuple[str, None]:
    import io
    from docx import Document
    doc = Document(io.BytesIO(contents))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs), None


def _extract_xlsx(contents: bytes) -> tuple[str, None]:
    import io
    import pandas as pd
    xls = pd.ExcelFile(io.BytesIO(contents))
    sheets = []
    for sheet in xls.sheet_names:
        df = xls.parse(sheet)
        sheets.append(f"## Sheet: {sheet}\n{df.to_string(index=False)}")
    return "\n\n".join(sheets), None


async def delete_document(db: AsyncSession, doc_id: int) -> None:
    """Delete a document record and its file from disk."""
    result = await db.execute(select(UploadedDocument).where(UploadedDocument.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # Remove file from disk (best-effort — don't fail if already gone)
    try:
        if doc.file_path and os.path.exists(doc.file_path):
            os.remove(doc.file_path)
    except OSError:
        pass
    await db.delete(doc)
    await db.flush()


async def get_document(db: AsyncSession, doc_id: int, project_id: int | None = None) -> UploadedDocument:
    stmt = select(UploadedDocument).where(UploadedDocument.id == doc_id)
    if project_id:
        stmt = stmt.where(UploadedDocument.project_id == project_id)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_documents(
    db: AsyncSession,
    project_id: int,
    skip: int = 0,
    limit: int = 100,
) -> list[UploadedDocument]:
    """List all documents for a project, newest first."""
    stmt = (
        select(UploadedDocument)
        .where(UploadedDocument.project_id == project_id)
        .order_by(UploadedDocument.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
