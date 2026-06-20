import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.models.test_case import TestCase, TestCaseHistory
from app.schemas.test_plan import TestCaseUpdate
from app.services import test_plan_service


class _ScalarResult:
    def __init__(self, *, count=0, duplicate_id=None):
        self.count = count
        self.duplicate_id = duplicate_id

    def scalar_one(self):
        return self.count

    def scalar_one_or_none(self):
        return self.duplicate_id


class _Scalars:
    def __init__(self, values):
        self.values = values

    def all(self):
        return self.values


class _ListResult:
    def __init__(self, values=None):
        self.values = values or []

    def scalars(self):
        return _Scalars(self.values)


class _FakeDB:
    def __init__(self, *, duplicate_external=False, mappings=None):
        self.duplicate_external = duplicate_external
        self.mappings = mappings or []
        self.execute_calls = 0
        self.added = []
        self.statements = []

    async def execute(self, _stmt):
        self.execute_calls += 1
        self.statements.append(_stmt)
        statement_text = str(_stmt)
        if self.mappings:
            return _ListResult(self.mappings)
        if "lower(test_cases.execution_mode)" in statement_text:
            return _ListResult([])
        if self.execute_calls == 1 and not self.duplicate_external:
            return _ScalarResult(count=0)
        return _ScalarResult(duplicate_id=99 if self.duplicate_external else None)

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


def _case(**overrides):
    data = {
        "id": 10,
        "project_id": 1,
        "created_by": 1,
        "test_case_id": "TC-0010",
        "title": "Validate eSIM activation",
        "priority": "Medium",
        "severity": "Medium",
        "automation_candidate": True,
        "execution_mode": "hybrid",
        "automation_eligible": "yes",
        "automation_status": "mapping_required",
        "status": "draft",
    }
    data.update(overrides)
    return TestCase(**data)


def test_patch_update_persists_fields_and_creates_history():
    async def run():
        db = _FakeDB()
        tc = _case()
        updated = await test_plan_service.update_test_case(
            db,
            tc,
            TestCaseUpdate(
                priority="High",
                mode="automated",
                automation_status="automated",
                external_tool="Mock",
                suite_id="REGRESSION",
                external_tc_id="EXT-10",
                jira_final_status="passed",
                comment="Ready for automation",
            ),
            user_id=7,
        )
        return db, updated

    import anyio

    db, updated = anyio.run(run)

    assert updated.priority == "High"
    assert updated.execution_mode == "automated"
    assert updated.automation_status == "automated"
    assert updated.external_tc_id == "EXT-10"
    assert updated.jira_final_status == "passed"
    history_fields = {row.field_name for row in db.added if isinstance(row, TestCaseHistory)}
    assert {"priority", "execution_mode", "automation_status", "external_tc_id", "jira_final_status"} <= history_fields


@pytest.mark.parametrize(
    "updates, detail",
    [
        (TestCaseUpdate(status="unknown"), "Invalid status"),
        (TestCaseUpdate(mode="manual", automation_status="automated", external_tc_id="EXT-1"), "Manual test cases"),
        (TestCaseUpdate(automation_eligible="no", automation_status="automated", external_tc_id="EXT-1"), "Automation-ineligible"),
        (TestCaseUpdate(mode="automated", automation_eligible="yes", automation_status="automated"), "requires external_tc_id"),
    ],
)
def test_patch_rejects_invalid_metadata_transitions(updates, detail):
    async def run():
        with pytest.raises(HTTPException) as exc:
            await test_plan_service.update_test_case(_FakeDB(), _case(), updates, user_id=7)
        return exc.value

    import anyio

    exc = anyio.run(run)

    assert exc.status_code in {409, 422}
    assert detail in str(exc.detail)


def test_duplicate_external_tc_id_is_rejected_within_project_tool_suite():
    async def run():
        with pytest.raises(HTTPException) as exc:
            await test_plan_service.update_test_case(
                _FakeDB(duplicate_external=True),
                _case(),
                TestCaseUpdate(external_tool="Mock", suite_id="REGRESSION", external_tc_id="EXT-10"),
                user_id=7,
            )
        return exc.value

    import anyio

    exc = anyio.run(run)

    assert exc.status_code == 409
    assert "external_tc_id already exists" in exc.detail


def test_patch_schema_rejects_invalid_external_url():
    with pytest.raises(ValidationError):
        TestCaseUpdate(external_tc_url="ftp://invalid.example")


def test_automation_only_query_enforces_automated_and_eligible():
    async def run():
        db = _FakeDB()
        await test_plan_service.list_test_cases(db, 1, status="approved", automation_only=True)
        return str(db.statements[0])

    import anyio

    statement = anyio.run(run)

    assert "lower(test_cases.execution_mode)" in statement
    assert "lower(test_cases.automation_eligible)" in statement


def test_changing_to_manual_normalizes_and_deactivates_mapping():
    class Mapping:
        is_active = True
        automation_status = "automated"

    async def run():
        mapping = Mapping()
        tc = _case(execution_mode="automated", automation_eligible="yes", automation_status="automated", external_tc_id="EXT-10")
        updated = await test_plan_service.update_test_case(
            _FakeDB(mappings=[mapping]),
            tc,
            TestCaseUpdate(mode="manual"),
            user_id=7,
        )
        return updated, mapping

    import anyio

    updated, mapping = anyio.run(run)

    assert updated.execution_mode == "manual"
    assert updated.automation_eligible == "no"
    assert updated.automation_status == "not_required"
    assert updated.automation_ready is False
    assert mapping.is_active is False
    assert mapping.automation_status == "not_required"


def test_changing_to_automated_and_eligible_sets_mapping_required():
    async def run():
        tc = _case(execution_mode="manual", automation_eligible="no", automation_status="not_required")
        return await test_plan_service.update_test_case(
            _FakeDB(),
            tc,
            TestCaseUpdate(mode="automated", automation_eligible="yes"),
            user_id=7,
        )

    import anyio

    updated = anyio.run(run)

    assert updated.execution_mode == "automated"
    assert updated.automation_eligible == "yes"
    assert updated.automation_status == "mapping_required"
