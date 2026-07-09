import anyio

from app.models.coverage_matrix import CoverageMatrixEntry
from app.models.test_case import TestCase
from app.services import coverage_matrix_service as svc


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _FakeDB:
    def __init__(self, *, existing_entry=None):
        self._entry = existing_entry
        self.added = []
        self.flushed = 0

    async def execute(self, _stmt):
        return _ScalarResult(self._entry)

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 1
        self.added.append(obj)
        self._entry = obj  # subsequent get_entry() calls see the new row

    async def flush(self):
        self.flushed += 1


def test_case_class_from_scenario_type_maps_known_types():
    assert svc.case_class_from_scenario_type("positive") == "positive"
    assert svc.case_class_from_scenario_type("edge") == "boundary"
    assert svc.case_class_from_scenario_type("security") == "exception"
    assert svc.case_class_from_scenario_type(None) is None
    assert svc.case_class_from_scenario_type("unknown_type") == "positive"


def test_seed_from_test_case_creates_row_when_absent():
    db = _FakeDB(existing_entry=None)
    tc = TestCase(
        id=100, project_id=1, created_by=1, test_case_id="TC-0001", title="T",
        requirement_id=10, scenario_id=20, test_type="functional", automation_eligible="no",
    )

    async def run():
        return await svc.seed_from_test_case(db, project_id=1, test_case=tc, case_class="positive")

    entry = anyio.run(run)
    assert entry.test_case_id == 100
    assert entry.requirement_id == 10
    assert entry.scenario_id == 20
    assert entry.case_class == "positive"
    assert entry in db.added


def test_record_script_linked_skips_when_no_baseline_row():
    db = _FakeDB(existing_entry=None)

    async def run():
        await svc.record_script_linked(db, test_case_id=100, script_id=5)

    anyio.run(run)
    assert db.added == []  # no row created — refresh calls never guess


def test_record_script_linked_updates_existing_row():
    entry = CoverageMatrixEntry(id=1, project_id=1, test_case_id=100)
    db = _FakeDB(existing_entry=entry)

    async def run():
        await svc.record_script_linked(db, test_case_id=100, script_id=5)

    anyio.run(run)
    assert entry.script_id == 5


def test_record_defect_linked_sets_defect_linked_flag():
    entry = CoverageMatrixEntry(id=1, project_id=1, test_case_id=100)
    db = _FakeDB(existing_entry=entry)

    async def run():
        await svc.record_defect_linked(db, test_case_id=100, defect_id=9)

    anyio.run(run)
    assert entry.defect_id == 9
    assert entry.defect_linked is True
