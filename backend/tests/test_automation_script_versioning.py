import anyio

from app.models.automation_script import AutomationScript
from app.services import automation_service


class _FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None


def test_create_new_version_links_parent_and_increments_version():
    db = _FakeDB()
    parent = AutomationScript(
        id=10, project_id=1, test_case_id=5, created_by=1, script_id="AS-0010",
        framework="playwright", code="old code", file_path="specs/old.spec.ts",
        version=1, status="static_passed", agent_run_id=99,
    )

    async def run():
        return await automation_service.create_new_version(
            db, parent,
            code="new code",
            compiled_files={"specs/new.spec.ts": "new code"},
            contract={"testCaseId": "TC-1"},
        )

    child = anyio.run(run)

    assert child.version == 2
    assert child.parent_script_id == 10
    assert child.code == "new code"
    assert child.project_id == parent.project_id
    assert child.test_case_id == parent.test_case_id
    assert child.status == "generated"
    assert child in db.added
    # Parent row must be untouched — rollback guarantee (ADR-001).
    assert parent.code == "old code"
    assert parent.version == 1
    assert parent.status == "static_passed"


def test_create_new_version_chains_across_multiple_versions():
    db = _FakeDB()
    v1 = AutomationScript(
        id=1, project_id=1, created_by=1, script_id="AS-0001", framework="playwright",
        code="v1", version=1, status="static_passed",
    )

    async def run():
        v2 = await automation_service.create_new_version(db, v1, code="v2")
        v3 = await automation_service.create_new_version(db, v2, code="v3")
        return v2, v3

    v2, v3 = anyio.run(run)

    assert v2.version == 2
    assert v3.version == 3
    assert v3.parent_script_id == v2.id
    assert v1.code == "v1"  # still restorable, never mutated
