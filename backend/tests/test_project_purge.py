"""The project purge plan must order deletes child-before-parent.

Regression: the old hand-maintained list deleted execution_runs before
test_cases, so fk_test_cases_last_execution_run_id (NO ACTION) aborted the whole
delete with a 500 and no project could be removed.
"""
import pytest

from app.services.project_purge import _order_children_first, project_purge_plan


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeCatalog:
    """Stands in for pg_catalog: answers the two introspection queries."""

    def __init__(self, scoped, edges):
        self.scoped = scoped
        self.edges = edges

    async def execute(self, statement, _params=None):
        sql = str(statement)
        if "confrelid = 'projects'::regclass" in sql:
            return _Result(self.scoped)
        return _Result(self.edges)


def _tables_in(plan):
    return [str(stmt).strip().split()[2] for stmt in plan]


@pytest.mark.asyncio
async def test_referencing_table_is_deleted_before_the_table_it_points_at():
    db = _FakeCatalog(
        scoped=[
            ("execution_runs", "project_id", b"c"),
            ("test_cases", "project_id", b"c"),
            ("test_case_history", "project_id", b"a"),
        ],
        edges=[
            # test_cases.last_execution_run_id -> execution_runs (NO ACTION)
            ("test_cases", "execution_runs"),
            ("test_case_history", "test_cases"),
        ],
    )

    tables = _tables_in(await project_purge_plan(db))

    assert tables.index("test_case_history") < tables.index("test_cases")
    assert tables.index("test_cases") < tables.index("execution_runs")
    assert tables[-1] == "projects"


@pytest.mark.asyncio
async def test_set_null_tables_keep_their_rows():
    db = _FakeCatalog(
        scoped=[
            ("test_cases", "project_id", b"c"),
            # ON DELETE SET NULL: the row outlives the project by design.
            ("daily_work_plans", "project_id", b"n"),
        ],
        edges=[],
    )

    tables = _tables_in(await project_purge_plan(db))

    assert "daily_work_plans" not in tables
    assert tables == ["test_cases", "projects"]


@pytest.mark.asyncio
async def test_every_scoped_table_is_deleted_once_per_referencing_column():
    db = _FakeCatalog(
        scoped=[
            ("assistant_conversations", "project_id", b"c"),
            ("recording_segments", "project_id", b"c"),
        ],
        edges=[],
    )

    plan = await project_purge_plan(db)

    assert _tables_in(plan) == ["assistant_conversations", "recording_segments", "projects"]
    assert all(":project_id" in str(stmt) for stmt in plan)


def test_ordering_is_stable_for_unrelated_tables():
    tables = {"b_table", "a_table", "c_table"}

    assert _order_children_first(tables, []) == ["a_table", "b_table", "c_table"]


def test_a_foreign_key_cycle_still_emits_every_table():
    """A cycle cannot be ordered; emit everything and let the database object."""
    tables = {"one", "two"}
    edges = [("one", "two"), ("two", "one")]

    assert sorted(_order_children_first(tables, edges)) == ["one", "two"]
