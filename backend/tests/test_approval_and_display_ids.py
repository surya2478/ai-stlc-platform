import anyio

from app.services.approval_service import create_approval_action
from app.services.display_id_service import display_id, temporary_id


class FakeDB:
    def __init__(self):
        self.added = []

    def add(self, obj):
        self.added.append(obj)

    async def flush(self):
        return None


def test_display_ids_use_temporary_and_row_id_values():
    temp = temporary_id("TC")

    assert temp.startswith("TC-TMP-")
    assert display_id("TC", 42) == "TC-0042"


def test_create_approval_action_is_immutable_audit_entry():
    db = FakeDB()

    async def run():
        return await create_approval_action(
            db,
            project_id=10,
            user_id=20,
            entity_type="test_case",
            entity_id=30,
            action="reject",
            notes="Needs clearer expected result",
        )

    entry = anyio.run(run)

    assert db.added == [entry]
    assert entry.action_type == "reject_test_case"
    assert entry.decision == "rejected"
    assert entry.notes == "Needs clearer expected result"
