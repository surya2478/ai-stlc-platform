import io

import anyio
import pytest
from fastapi import HTTPException
from starlette.datastructures import UploadFile

from app.models.test_data import TestData as TestDataModel
from app.schemas.test_data import (
    TestDataGenerateRequest as TestDataGenerateRequestSchema,
    TestDataImportMetadata as TestDataImportMetadataSchema,
    TestDataMaskRequest as TestDataMaskRequestSchema,
)
from app.services import test_data_generation_service, test_data_import_service, test_data_service


class FakeDB:
    def __init__(self):
        self.added = []
        self._next_id = 100

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        for obj in self.added:
            if getattr(obj, "id", None) is None:
                setattr(obj, "id", self._next_id)
                self._next_id += 1
        return None


def make_item(**overrides):
    base = dict(
        id=1,
        project_id=10,
        created_by=20,
        data_id="TD-0001",
        name="Subscriber Seed",
        data_type="Subscriber",
        source_type="manual",
        status="approved",
        approval_status="approved",
        telecom_domain="Mobile",
        test_phase="SIT",
        environment="SIT",
        version=1,
        data_payload_json={"msisdn": "971501234567", "plan_code": "PLAN_5G"},
        sample_preview_json={"msisdn": "***", "plan_code": "PLAN_5G"},
        sensitive_fields_json=["msisdn"],
        privacy_level="confidential",
        contains_pii=True,
        masking_status="pending",
        synthetic_generation_status="not_required",
        reservation_status="available",
        usage_count=0,
        quality_status="not_checked",
        quality_issues_json=[],
        metadata_=None,
        agent_run_id=None,
        linked_jira_issue_key=None,
    )
    base.update(overrides)
    return TestDataModel(**base)


def test_validate_marks_masking_gap_invalid():
    db = FakeDB()
    item = make_item(masking_status="not_required")

    async def run():
        return await test_data_service.validate_test_data(db, item)

    validated = anyio.run(run)

    assert validated.quality_status == "invalid"
    assert any(issue["code"] == "masking_required" for issue in validated.quality_issues_json)


def test_masking_updates_payload_and_status():
    db = FakeDB()
    item = make_item()

    async def run():
        return await test_data_service.mask_test_data(
            db,
            item,
            TestDataMaskRequestSchema(fields=["msisdn"], keep_last=3),
            user_id=77,
        )

    masked = anyio.run(run)

    assert masked.masking_status == "masked"
    assert masked.data_payload_json["msisdn"].endswith("567")
    assert "X" in masked.data_payload_json["msisdn"]


def test_reservation_prevents_second_user_claim():
    db = FakeDB()
    item = make_item(masking_status="masked", quality_status="valid")

    async def run():
        await test_data_service.reserve_test_data(db, item, user_id=11, reserved_for_execution_id=90, duration_minutes=60)
        with pytest.raises(HTTPException) as exc:
            await test_data_service.reserve_test_data(db, item, user_id=12, reserved_for_execution_id=91, duration_minutes=60)
        return exc.value

    exc = anyio.run(run)

    assert exc.status_code == 409


def test_release_requires_owner():
    db = FakeDB()
    item = make_item(masking_status="masked", quality_status="valid", reservation_status="reserved", reserved_by=11)

    async def run():
        with pytest.raises(HTTPException) as exc:
            await test_data_service.release_test_data(db, item, user_id=12)
        return exc.value

    exc = anyio.run(run)

    assert exc.status_code == 403


def test_consume_marks_usage():
    db = FakeDB()
    item = make_item(masking_status="masked", quality_status="valid", reservation_status="reserved", reserved_by=11)

    async def run():
        return await test_data_service.consume_test_data(db, item, user_id=11)

    consumed = anyio.run(run)

    assert consumed.status == "consumed"
    assert consumed.reservation_status == "consumed"
    assert consumed.usage_count == 1
    assert consumed.last_used_at is not None


def test_approve_writes_immutable_approval_action():
    db = FakeDB()
    item = make_item(status="pending_approval", approval_status="pending_approval", masking_status="masked", quality_status="valid")

    async def run():
        return await test_data_service.approve_test_data(db, item, user_id=42, notes="Reviewed and approved")

    approved = anyio.run(run)

    assert approved.approval_status == "approved"
    assert approved.approved_by == 42
    assert any(getattr(entry, "entity_type", None) == "test_data" for entry in db.added)


def test_import_metadata_rejects_public_pii():
    with pytest.raises(ValueError):
        TestDataImportMetadataSchema(
            data_type="Subscriber",
            telecom_domain="Mobile",
            test_phase="SIT",
            environment="SIT",
            contains_pii=True,
            privacy_level="public",
        )


def test_parse_csv_supports_quoted_commas():
    headers, rows = test_data_import_service._parse_csv(
        b'name,notes\nalpha,"hello, world"\n'
    )

    assert headers == ["name", "notes"]
    assert rows[0]["notes"] == "hello, world"


def test_parse_csv_rejects_duplicate_headers():
    with pytest.raises(HTTPException) as exc:
        test_data_import_service._parse_csv(b"name,name\none,two\n")

    assert exc.value.status_code == 422


def test_create_external_generation_request_stores_mapping_fields(monkeypatch):
    db = FakeDB()

    async def fake_validate(*args, **kwargs):
        return None

    monkeypatch.setattr(test_data_generation_service, "_validate_project_links", fake_validate)

    request = TestDataGenerateRequestSchema(
        name="Billing Negative Data",
        data_type="Order",
        telecom_domain="Billing",
        test_phase="SIT",
        environment="SIT",
        number_of_records=5,
        generation_mode="negative",
        external_tool="Other",
        external_suite_id="SUITE-1",
        external_dataset_id="DATA-9",
        request_notes="Create invalid charge cases",
        priority="High",
    )

    class User:
        id = 7
        role = "qa_lead"

    async def run():
        return await test_data_generation_service.create_external_generation_request(
            db,
            10,
            request,
            User(),
        )

    item = anyio.run(run)

    assert item.external_tool == "Other"
    assert item.external_suite_id == "SUITE-1"
    assert item.external_dataset_id == "DATA-9"
    assert item.generation_status == "pending_external_generation"
    assert item.source_type == "external_tool"
    assert any(getattr(entry, "action_type", None) == "request_test_data_generation" for entry in db.added)


def test_create_import_preview_rejects_empty_upload(monkeypatch):
    db = FakeDB()

    async def fake_validate(*args, **kwargs):
        return None

    monkeypatch.setattr(test_data_import_service, "_validate_project_links", fake_validate)

    metadata = TestDataImportMetadataSchema(
        data_type="Subscriber",
        telecom_domain="Mobile",
        test_phase="SIT",
        environment="SIT",
    )

    async def run():
        empty = UploadFile(filename="empty.csv", file=io.BytesIO(b""))
        await test_data_import_service.create_import_preview(db, 10, 3, empty, metadata)

    with pytest.raises(HTTPException) as exc:
        anyio.run(run)

    assert exc.value.status_code == 422
