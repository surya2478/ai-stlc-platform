"""Background document extraction tasks."""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from app.config import get_settings
from app.database import AsyncSessionLocal
from app.models.document import UploadedDocument
from app.services.document_service import extract_text
from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


async def _extract_document_text(doc_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(UploadedDocument).where(UploadedDocument.id == doc_id))
        doc = result.scalar_one_or_none()
        if not doc:
            raise ValueError(f"Document {doc_id} not found")

        try:
            extracted, page_count = extract_text(doc.file_path, doc.file_type)
            doc.extracted_text = extracted
            doc.page_count = page_count
            doc.status = "processed"
            doc.metadata_ = {**(doc.metadata_ or {}), "extraction_status": "completed"}
            await db.commit()
            return {"document_id": doc_id, "status": "processed"}
        except Exception as exc:
            logger.exception("Document extraction failed: doc_id=%s", doc_id)
            doc.status = "failed"
            doc.metadata_ = {**(doc.metadata_ or {}), "extraction_error": str(exc)}
            await db.commit()
            return {"document_id": doc_id, "status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="document_tasks.extract_document_text", max_retries=2)
def extract_document_text(self, doc_id: int):
    result = asyncio.run(_extract_document_text(doc_id))
    # Enqueue RAG indexing after successful extraction
    if result.get("status") == "processed" and settings.rag_enabled:
        from app.worker.tasks.rag_tasks import task_index_document
        task_index_document.delay(doc_id)
    return result
