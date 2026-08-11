"""Screen 1 intake: batches, their documents, and the application URL."""
from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import get_settings
from app.models.document import UploadedDocument
from app.models.project_application import ProjectApplication
from app.models.test_automation_studio import (
    TasCoverageAssessment,
    TasIntakeBatch,
    TasIntakeDocument,
)
from app.schemas.test_automation_studio import (
    IntakeBatchCreate,
    IntakeBatchUpdate,
    IntakeDocumentAttach,
)

settings = get_settings()


async def list_batches(db: AsyncSession, project_id: int) -> list[TasIntakeBatch]:
    result = await db.execute(
        select(TasIntakeBatch)
        .options(selectinload(TasIntakeBatch.documents).selectinload(TasIntakeDocument.document))
        .where(TasIntakeBatch.project_id == project_id)
        .order_by(TasIntakeBatch.created_at.desc())
    )
    return list(result.scalars().unique().all())


async def get_batch_or_404(db: AsyncSession, batch_id: int) -> TasIntakeBatch:
    result = await db.execute(
        select(TasIntakeBatch)
        .options(selectinload(TasIntakeBatch.documents).selectinload(TasIntakeDocument.document))
        .where(TasIntakeBatch.id == batch_id)
        # populate_existing is required, not decorative. This is called right
        # after attaching or detaching a document, when the batch is already in
        # the session's identity map with `documents` loaded — and an eager
        # load will not overwrite an already-loaded collection without it. The
        # symptom was an upload returning 201 with an empty `documents` list
        # while the row was in fact attached.
        .execution_options(populate_existing=True)
    )
    batch = result.scalars().unique().one_or_none()
    if batch is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intake batch not found")
    return batch


async def _resolve_application(
    db: AsyncSession, *, project_id: int, application_id: int | None
) -> ProjectApplication | None:
    if application_id is None:
        return None
    result = await db.execute(
        select(ProjectApplication).where(
            ProjectApplication.id == application_id,
            ProjectApplication.project_id == project_id,
        )
    )
    application = result.scalar_one_or_none()
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected application does not belong to this project",
        )
    return application


async def _sync_application_url(
    db: AsyncSession,
    *,
    application: ProjectApplication | None,
    url: str | None,
    environment: str,
    user_id: int,
) -> None:
    """Write the batch's URL back into the application's environment_urls.

    This is what "complement current project settings" means in practice: the
    URL typed on Screen 1 becomes the project's URL for that environment, so
    execution and the other automation modules resolve the same value rather
    than the studio holding a private copy that silently diverges. An
    application that already has a URL for this environment is left alone —
    Screen 1 is an intake screen, not the place to silently repoint a
    configured environment.
    """
    if application is None or not url:
        return
    urls = dict(application.environment_urls or {})
    if urls.get(environment):
        return
    urls[environment] = url
    application.environment_urls = urls
    application.updated_by = user_id
    db.add(application)


async def create_batch(
    db: AsyncSession, *, project_id: int, body: IntakeBatchCreate, user_id: int
) -> TasIntakeBatch:
    application = await _resolve_application(
        db, project_id=project_id, application_id=body.application_id
    )
    batch = TasIntakeBatch(
        project_id=project_id,
        name=body.name.strip(),
        description=body.description,
        application_id=body.application_id,
        application_url=body.application_url,
        application_environment=body.application_environment or "qa",
        status="draft",
        created_by=user_id,
        updated_by=user_id,
    )
    db.add(batch)
    await _sync_application_url(
        db,
        application=application,
        url=body.application_url,
        environment=batch.application_environment,
        user_id=user_id,
    )
    await db.commit()
    return await get_batch_or_404(db, batch.id)


async def update_batch(
    db: AsyncSession, *, batch: TasIntakeBatch, body: IntakeBatchUpdate, user_id: int
) -> TasIntakeBatch:
    if body.application_id is not None:
        await _resolve_application(db, project_id=batch.project_id, application_id=body.application_id)

    for field in ("name", "description", "application_id", "application_url", "application_environment"):
        value = getattr(body, field)
        if value is not None:
            setattr(batch, field, value.strip() if isinstance(value, str) and field == "name" else value)

    batch.updated_by = user_id
    db.add(batch)

    application = await _resolve_application(
        db, project_id=batch.project_id, application_id=batch.application_id
    )
    await _sync_application_url(
        db,
        application=application,
        url=batch.application_url,
        environment=batch.application_environment,
        user_id=user_id,
    )
    await db.commit()
    return await get_batch_or_404(db, batch.id)


async def delete_batch(db: AsyncSession, batch: TasIntakeBatch) -> None:
    await db.delete(batch)
    await db.commit()


async def attach_documents(
    db: AsyncSession, *, batch: TasIntakeBatch, documents: list[IntakeDocumentAttach]
) -> TasIntakeBatch:
    """Attach already-uploaded documents to a batch, tagged with their role."""
    existing_count = (
        await db.execute(
            select(func.count(TasIntakeDocument.id)).where(TasIntakeDocument.batch_id == batch.id)
        )
    ).scalar_one()
    if existing_count + len(documents) > settings.tas_max_documents_per_batch:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"A batch may hold at most {settings.tas_max_documents_per_batch} documents "
                f"(this batch already has {existing_count})."
            ),
        )

    requested_ids = [item.document_id for item in documents]
    owned = (
        await db.execute(
            select(UploadedDocument.id).where(
                UploadedDocument.id.in_(requested_ids),
                UploadedDocument.project_id == batch.project_id,
            )
        )
    ).scalars().all()
    owned_ids = set(owned)
    missing = [doc_id for doc_id in requested_ids if doc_id not in owned_ids]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Documents not found in this project: {missing}",
        )

    already_linked = set(
        (
            await db.execute(
                select(TasIntakeDocument.document_id).where(TasIntakeDocument.batch_id == batch.id)
            )
        )
        .scalars()
        .all()
    )
    for item in documents:
        if item.document_id in already_linked:
            continue
        db.add(
            TasIntakeDocument(
                batch_id=batch.id,
                document_id=item.document_id,
                doc_role=item.doc_role,
            )
        )
        already_linked.add(item.document_id)

    # Re-attaching documents invalidates whatever the last assessment
    # concluded, so the batch drops back to draft rather than continuing to
    # advertise a stale "assessed" state against a changed input set.
    if batch.status == "assessed":
        batch.status = "draft"
        db.add(batch)

    await db.commit()
    return await get_batch_or_404(db, batch.id)


async def set_document_role(
    db: AsyncSession, *, batch: TasIntakeBatch, link_id: int, doc_role: str
) -> TasIntakeBatch:
    link = (
        await db.execute(
            select(TasIntakeDocument).where(
                TasIntakeDocument.id == link_id, TasIntakeDocument.batch_id == batch.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document is not in this batch")
    link.doc_role = doc_role
    db.add(link)
    if batch.status == "assessed":
        batch.status = "draft"
        db.add(batch)
    await db.commit()
    return await get_batch_or_404(db, batch.id)


async def detach_document(db: AsyncSession, *, batch: TasIntakeBatch, link_id: int) -> TasIntakeBatch:
    link = (
        await db.execute(
            select(TasIntakeDocument).where(
                TasIntakeDocument.id == link_id, TasIntakeDocument.batch_id == batch.id
            )
        )
    ).scalar_one_or_none()
    if link is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document is not in this batch")
    await db.delete(link)
    if batch.status == "assessed":
        batch.status = "draft"
        db.add(batch)
    await db.commit()
    return await get_batch_or_404(db, batch.id)


async def latest_assessment(db: AsyncSession, batch_id: int) -> TasCoverageAssessment | None:
    result = await db.execute(
        select(TasCoverageAssessment)
        .where(TasCoverageAssessment.batch_id == batch_id)
        .order_by(TasCoverageAssessment.version.desc())
        .limit(1)
    )
    return result.scalars().first()


def serialize_document(link: TasIntakeDocument) -> dict:
    doc = link.document
    # Text extraction runs asynchronously on the worker after upload, so the
    # authority on readiness is the uploaded document's own status plus whether
    # any text actually landed — not this link row, which only records what the
    # last assessment consumed. Without this the UI would offer "Assess" the
    # instant a file finished uploading and the run would fail on empty text.
    doc_status = getattr(doc, "status", None) or "unknown"
    has_text = bool((getattr(doc, "extracted_text", None) or "").strip())
    return {
        "id": link.id,
        "batch_id": link.batch_id,
        "document_id": link.document_id,
        "doc_role": link.doc_role,
        "extraction_status": link.extraction_status,
        "extraction_error": link.extraction_error,
        "document_status": doc_status,
        "text_available": has_text,
        "ready_for_assessment": has_text or doc_status == "processed",
        "extracted_requirement_count": link.extracted_requirement_count,
        "extracted_test_case_count": link.extracted_test_case_count,
        "original_filename": getattr(doc, "original_filename", None),
        "file_type": getattr(doc, "file_type", None),
        "file_size_bytes": getattr(doc, "file_size_bytes", None),
        "created_at": link.created_at,
    }


def serialize_batch(batch: TasIntakeBatch) -> dict:
    return {
        "id": batch.id,
        "project_id": batch.project_id,
        "name": batch.name,
        "description": batch.description,
        "application_id": batch.application_id,
        "application_url": batch.application_url,
        "application_environment": batch.application_environment,
        "status": batch.status,
        "status_error": batch.status_error,
        "created_by": batch.created_by,
        "created_at": batch.created_at,
        "updated_at": batch.updated_at,
        "documents": [serialize_document(link) for link in batch.documents],
    }
