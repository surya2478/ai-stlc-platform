"""
Document upload and retrieval endpoints.
POST   /documents/upload     — upload a file and extract text
GET    /documents/{id}       — get document details + extracted text
GET    /documents/project/{pid} — list documents for a project
DELETE /documents/{id}       — delete document + file from disk
"""
from fastapi import APIRouter, UploadFile, File, Query, status

from app.api.deps import CurrentUser, DBSession, require_entity_permission, require_entity_project_access, require_permission, require_project_access
from app.schemas.document import DocumentOut, DocumentListOut
from app.services import document_service
from app.services.rbac_service import MANAGE_PROJECT

router = APIRouter()


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(..., description="Project to attach document to"),
    file: UploadFile = File(...),
):
    """Upload a document (PDF/DOCX/TXT/MD/CSV) and extract its text."""
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    return await document_service.upload_document(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        file=file,
    )


@router.get("/project/{project_id}", response_model=list[DocumentListOut])
async def list_project_documents(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List all documents for a project."""
    await require_project_access(project_id, current_user, db)
    return await document_service.list_documents(db, project_id, skip, limit)


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(
    doc_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Get a document by ID."""
    doc = await document_service.get_document(db, doc_id)
    await require_entity_permission(doc, MANAGE_PROJECT, current_user, db)
    return doc


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    db: DBSession,
    current_user: CurrentUser,
):
    """Delete a document and its stored file."""
    doc = await document_service.get_document(db, doc_id)
    await require_entity_project_access(doc, current_user, db)
    await document_service.delete_document(db, doc_id)
    await db.commit()
