import pytest
from fastapi import HTTPException

from app.services.document_service import sanitize_filename, validate_file_signature


def test_sanitize_filename_removes_paths_and_unsafe_chars():
    assert sanitize_filename("../../Quarterly Plan!!.pdf") == "Quarterly_Plan_.pdf"
    assert sanitize_filename("...") == "upload"


def test_validate_file_signature_accepts_expected_headers():
    validate_file_signature("pdf", b"%PDF-1.7\n")
    validate_file_signature("docx", b"PK\x03\x04rest")
    validate_file_signature("txt", b"hello world")


def test_validate_file_signature_rejects_mismatched_pdf():
    with pytest.raises(HTTPException) as exc:
        validate_file_signature("pdf", b"not a pdf")

    assert exc.value.status_code == 415
