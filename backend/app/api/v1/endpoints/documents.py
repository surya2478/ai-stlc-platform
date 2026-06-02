"""
Document upload and retrieval endpoints.
POST   /documents/upload     — upload a file and extract text
GET    /documents/{id}       — get document details + extracted text
GET    /documents/project/{pid} — list documents for a project
DELETE /documents/{id}       — delete document + file from disk
"""
from fastapi import APIRouter, UploadFile, File, Query, status

from app.api.deps import DBSession, OptionalUser
from app.schemas.document import DocumentOut, DocumentListOut
from app.services import document_service

router = APIRouter()


@router.post("/upload", response_model=DocumentOut, status_code=201)
async def upload_document(
    db: DBSession,
    current_user: OptionalUser,
    project_id: int = Query(..., description="Project to attach document to"),
    file: UploadFile = File(...),
):
    """Upload a document (PDF/DOCX/TXT/MD/CSV) and extract its text."""
    user_id = current_user.id if current_user else 1
    return await document_service.upload_document(
        db=db,
        project_id=project_id,
        user_id=user_id,
        file=file,
    )


@router.get("/project/{project_id}", response_model=list[DocumentListOut])
async def list_project_documents(
    project_id: int,
    db: DBSession,
    current_user: OptionalUser,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List all documents for a project."""
    return await document_service.list_documents(db, project_id, skip, limit)


@router.get("/{doc_id}", response_model=DocumentOut)
async def get_document(
    doc_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    """Get a document by ID."""
    return await document_service.get_document(db, doc_id)


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    db: DBSession,
    current_user: OptionalUser,
):
    """Delete a document and its stored file."""
    await document_service.delete_document(db, doc_id)
    await db.commit()
