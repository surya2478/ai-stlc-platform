"""Wave 3 / P0-06: evidence masking, integrity and serving policy (AUT-014).

`views.py` documented a masked download endpoint that did not exist, and
`sanitized` was permanently false because no code ever moved it. These cover the
service that finally does both, plus the two refusals that matter: content that
no longer matches its checksum, and binary artifacts no text pass can mask.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.config import Settings
from app.models.execution_command_center import ExecutionRunEvidence
from app.services.execution_command_center import evidence_service as svc


def _settings(**overrides) -> Settings:
    overrides.setdefault("app_secret_key", "test-secret-key-with-sufficient-length-1234")
    return Settings(**overrides)


# ── Masking ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "raw",
    [
        "Authorization: Bearer abcdef0123456789ABCDEF",
        '{"api_key":"sk-live-9f8e7d6c5b4a"}',
        "GET /orders?access_token=zzzzzzzzzzzz HTTP/1.1",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dBjftJeZ4CVPmB92K27u",
        "customer contact was jane.doe@example.com",
        "SIM ICCID 8944500102030405060",
    ],
)
def test_common_secret_shapes_are_masked(raw):
    masked, hits = svc.mask_text(raw)
    assert hits > 0
    assert svc.REDACTED in masked


def test_masking_leaves_ordinary_content_alone():
    """Over-masking destroys the evidence's usefulness, so the rules have to be
    shaped tightly enough to leave normal log lines intact."""
    raw = "Order 4501 created for plan PREPAID_20 at 2026-08-01T09:15:00Z"
    masked, hits = svc.mask_text(raw)
    assert hits == 0
    assert masked == raw


def test_ordinary_ids_are_not_swallowed_by_the_digit_rule():
    """13-19 digits is the PAN/IMEI/ICCID band. A 10-digit order id must survive
    or every network log becomes unreadable."""
    masked, hits = svc.mask_text("order_id=1234567890 status=200")
    assert hits == 0
    assert masked == "order_id=1234567890 status=200"


def test_payload_masking_walks_nested_structures_and_spares_keys():
    payload = {
        "entries": [
            {"url": "https://api/x?token=abcdefgh", "status": 200},
            {"text": "user bob@example.com signed in"},
        ]
    }
    masked, hits = svc.mask_payload(payload)
    assert hits >= 2
    # Keys are field names; rewriting them corrupts the structure without
    # protecting anything.
    assert set(masked["entries"][0]) == {"url", "status"}
    assert masked["entries"][0]["status"] == 200
    assert svc.REDACTED in masked["entries"][0]["url"]
    assert svc.REDACTED in masked["entries"][1]["text"]


# ── Capture-time facts ──────────────────────────────────────────────────────


def test_capture_records_size_and_checksum_for_a_file(tmp_path):
    artifact = tmp_path / "run.log"
    artifact.write_bytes(b"hello world")
    row = ExecutionRunEvidence(evidence_type="log", status="captured", file_path=str(artifact))

    svc.record_artifact_facts(row)

    assert row.size_bytes == 11
    assert row.checksum_sha256 == hashlib.sha256(b"hello world").hexdigest()
    assert row.redaction_state == "pending"
    assert row.sanitized is False


def test_binary_evidence_is_marked_not_maskable_at_capture(tmp_path):
    artifact = tmp_path / "shot.png"
    artifact.write_bytes(b"\x89PNG\r\n")
    row = ExecutionRunEvidence(
        evidence_type="screenshot", status="captured", file_path=str(artifact)
    )
    svc.record_artifact_facts(row)
    assert row.redaction_state == "not_maskable"
    assert row.content_type == "image/png"


def test_a_vanished_artifact_leaves_facts_null_rather_than_guessing(tmp_path):
    row = ExecutionRunEvidence(
        evidence_type="log", status="captured", file_path=str(tmp_path / "gone.log")
    )
    svc.record_artifact_facts(row)
    assert row.checksum_sha256 is None
    assert row.size_bytes is None


# ── Resolution ──────────────────────────────────────────────────────────────


def test_uncaptured_evidence_reports_its_reason_instead_of_serving():
    row = ExecutionRunEvidence(
        evidence_type="screenshot",
        status="unavailable",
        unavailable_reason="The runner did not produce screenshot evidence for this test.",
    )
    with pytest.raises(svc.EvidenceError) as exc:
        svc.resolve(row, settings=_settings())
    assert exc.value.status_code == 409
    assert "did not produce" in exc.value.detail


def test_payload_evidence_is_masked_and_marked_sanitized():
    row = ExecutionRunEvidence(
        evidence_type="network",
        status="captured",
        payload={"entries": [{"url": "https://api/x?token=abcdefgh"}]},
    )
    resolved = svc.resolve(row, settings=_settings())

    assert resolved.masked and resolved.mask_hits >= 1
    assert svc.REDACTED in json.loads(resolved.content.decode())["entries"][0]["url"]
    # The flag that was stuck on false finally moves, and only via the pass.
    assert row.redaction_state == "masked"
    assert row.sanitized is True


def test_a_log_file_is_masked_on_the_way_out(tmp_path):
    artifact = tmp_path / "run.log"
    artifact.write_text("Authorization: Bearer abcdef0123456789", encoding="utf-8")
    row = ExecutionRunEvidence(
        evidence_type="log", status="captured", file_path=str(artifact)
    )
    svc.record_artifact_facts(row)

    resolved = svc.resolve(row, settings=_settings(file_storage_path=str(tmp_path)))

    assert svc.REDACTED in resolved.content.decode()
    assert resolved.integrity_verified
    assert row.sanitized is True


def test_a_tampered_artifact_is_refused_not_served(tmp_path):
    """The whole point of recording a checksum: bytes that changed after capture
    are not the evidence the run produced."""
    artifact = tmp_path / "run.log"
    artifact.write_text("original", encoding="utf-8")
    row = ExecutionRunEvidence(
        evidence_type="log", status="captured", file_path=str(artifact)
    )
    svc.record_artifact_facts(row)
    artifact.write_text("tampered", encoding="utf-8")

    with pytest.raises(svc.EvidenceError) as exc:
        svc.resolve(row, settings=_settings(file_storage_path=str(tmp_path)))
    assert exc.value.status_code == 409
    assert "checksum" in exc.value.detail


def test_an_artifact_outside_the_storage_root_is_refused(tmp_path):
    outside = tmp_path / "outside.log"
    outside.write_text("x", encoding="utf-8")
    root = tmp_path / "storage"
    root.mkdir()
    row = ExecutionRunEvidence(
        evidence_type="log", status="captured", file_path=str(outside)
    )
    with pytest.raises(svc.EvidenceError) as exc:
        svc.resolve(row, settings=_settings(file_storage_path=str(root)))
    assert exc.value.status_code == 403


def test_binary_evidence_is_refused_in_production_by_default(tmp_path):
    artifact = tmp_path / "shot.png"
    artifact.write_bytes(b"\x89PNG\r\n")
    row = ExecutionRunEvidence(
        evidence_type="screenshot", status="captured", file_path=str(artifact)
    )
    svc.record_artifact_facts(row)

    with pytest.raises(svc.EvidenceError) as exc:
        svc.resolve(
            row, settings=_settings(app_env="production", file_storage_path=str(tmp_path))
        )
    assert exc.value.status_code == 403
    assert "cannot be masked" in exc.value.detail


def test_binary_evidence_is_served_outside_production_and_says_it_is_unmasked(tmp_path):
    artifact = tmp_path / "shot.png"
    artifact.write_bytes(b"\x89PNG\r\n")
    row = ExecutionRunEvidence(
        evidence_type="screenshot", status="captured", file_path=str(artifact)
    )
    svc.record_artifact_facts(row)

    resolved = svc.resolve(
        row, settings=_settings(app_env="staging", file_storage_path=str(tmp_path))
    )

    assert resolved.content == b"\x89PNG\r\n"
    assert resolved.masked is False
    assert resolved.integrity_verified
    # It must never claim sanitization it did not perform.
    assert row.sanitized is False
    assert row.redaction_state == "not_maskable"


def test_explicit_opt_in_serves_binary_evidence_in_production(tmp_path):
    artifact = tmp_path / "shot.png"
    artifact.write_bytes(b"\x89PNG\r\n")
    row = ExecutionRunEvidence(
        evidence_type="screenshot", status="captured", file_path=str(artifact)
    )
    svc.record_artifact_facts(row)

    resolved = svc.resolve(
        row,
        settings=_settings(
            app_env="production",
            automation_evidence_allow_unmasked=True,
            file_storage_path=str(tmp_path),
        ),
    )
    assert resolved.masked is False
    assert resolved.content == b"\x89PNG\r\n"
