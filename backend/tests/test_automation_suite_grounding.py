"""Grounding matrix at its new (test_case, model) scope."""
from types import SimpleNamespace

import anyio

from app.services.automation_suite.grounding import build_grounding_matrix


class _ExecuteResult:
    def __init__(self, values):
        self._values = list(values)

    def scalars(self):
        return self

    def all(self):
        return list(self._values)


class _FakeDB:
    def __init__(self, by_table=None):
        self.by_table = by_table or {}

    async def execute(self, stmt):
        statement = str(stmt)
        for table, rows in self.by_table.items():
            if table in statement:
                return _ExecuteResult(rows)
        return _ExecuteResult([])


def _test_case(steps):
    return SimpleNamespace(id=10, steps=steps)


def test_every_step_is_missing_without_a_model():
    test_case = _test_case([{"step_number": 1, "action": "Open login"}, {"step_number": 2, "action": "Sign in"}])
    rows = anyio.run(lambda: build_grounding_matrix(_FakeDB(), test_case=test_case, model=None))
    assert len(rows) == 2
    assert all(r["status"] == "Missing" for r in rows)
    assert [r["step_number"] for r in rows] == [1, 2]
    assert all(r["external_validation"] == "NOT_EVALUATED" for r in rows)


def test_a_model_with_no_source_session_grounds_nothing():
    test_case = _test_case([{"step_number": 1, "action": "Open login"}])
    model = SimpleNamespace(id=9, source_session_id=None)
    rows = anyio.run(lambda: build_grounding_matrix(_FakeDB(), test_case=test_case, model=model))
    assert [r["status"] for r in rows] == ["Missing"]


def test_no_steps_yields_no_rows():
    rows = anyio.run(lambda: build_grounding_matrix(_FakeDB(), test_case=_test_case([]), model=None))
    assert rows == []


def test_a_missing_test_case_yields_no_rows():
    rows = anyio.run(lambda: build_grounding_matrix(_FakeDB(), test_case=None, model=None))
    assert rows == []


def test_a_fully_grounded_step_is_complete():
    test_case = _test_case([{"step_number": 1, "action": "Click submit"}])
    model = SimpleNamespace(id=9, source_session_id=4)
    action = SimpleNamespace(
        id=100,
        test_step_ref="1",
        target_screen_ref="screen-a",
        target_element_ref="element-b",
        evidence_refs=["cap-1", "cap-2"],
    )
    db = _FakeDB(
        {
            "discovery_actions": [action],
            "application_model_nodes": [
                SimpleNamespace(node_type="screen", external_ref="screen-a", display_name="Checkout", state="CONFIRMED"),
                SimpleNamespace(node_type="element", external_ref="element-b", display_name="Submit", state="CONFIRMED"),
            ],
            "network_events": [SimpleNamespace(action_id=100, method="POST", path="/api/orders")],
        }
    )
    rows = anyio.run(lambda: build_grounding_matrix(db, test_case=test_case, model=model))
    row = rows[0]
    assert row["status"] == "Complete"
    assert row["screen"] == "Checkout"
    assert row["element"] == "Submit"
    assert row["apis"] == ["POST /api/orders"]
    assert row["evidence_count"] == 2


def test_a_step_with_a_critical_model_gap_is_blocked():
    test_case = _test_case([{"step_number": 1, "action": "Click submit"}])
    model = SimpleNamespace(id=9, source_session_id=4)
    action = SimpleNamespace(
        id=100, test_step_ref="1", target_screen_ref="screen-a", target_element_ref=None, evidence_refs=[]
    )
    db = _FakeDB(
        {
            "discovery_actions": [action],
            "application_model_nodes": [],
            "application_model_gaps": [
                SimpleNamespace(gap_type="MISSING_ELEMENT", evidence={"action_id": 100})
            ],
        }
    )
    rows = anyio.run(lambda: build_grounding_matrix(db, test_case=test_case, model=model))
    assert rows[0]["status"] == "Blocked"


def test_an_unmatched_step_is_missing_even_when_others_ground():
    test_case = _test_case(
        [{"step_number": 1, "action": "Click submit"}, {"step_number": 2, "action": "Verify receipt"}]
    )
    model = SimpleNamespace(id=9, source_session_id=4)
    action = SimpleNamespace(
        id=100, test_step_ref="1", target_screen_ref="screen-a", target_element_ref=None, evidence_refs=[]
    )
    db = _FakeDB(
        {
            "discovery_actions": [action],
            "application_model_nodes": [
                SimpleNamespace(node_type="screen", external_ref="screen-a", display_name="Checkout", state="CONFIRMED")
            ],
        }
    )
    rows = anyio.run(lambda: build_grounding_matrix(db, test_case=test_case, model=model))
    assert [r["status"] for r in rows] == ["Complete", "Missing"]
