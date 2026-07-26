"""Suite service — the DB-facing layer.

Uses a fake session that dispatches on the queried table rather than on a
strict response queue. The retired engine's tests had to queue responses in
exact query order, which coupled them to the service's internals; because all
evaluation reads are now hoisted into `inheritance`, dispatching by table is
both sufficient and stable under refactoring.
"""
from types import SimpleNamespace

import anyio
import pytest

from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.services.automation_suite import suite_service as svc
from app.services.automation_suite.errors import AutomationSuiteError


class _ScalarsResult:
    def __init__(self, values):
        self._values = list(values)

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None


class _ExecuteResult:
    def __init__(self, values, *, scalar=None):
        self._values = list(values)
        self._scalar = scalar

    def scalars(self):
        return _ScalarsResult(self._values)

    def all(self):
        return list(self._values)

    def scalar(self):
        return self._scalar if self._scalar is not None else len(self._values)

    def one(self):
        return self._values[0] if self._values else (0, 0)


_TABLES = (
    "automation_suite_test_cases",
    "automation_suite_activity",
    "automation_suite_gaps",
    "automation_suites",
    "test_cases",
    "project_applications",
    "application_models",
    "application_model_gaps",
    "test_case_automation_classifications",
    "automation_scripts",
    "test_data",
    "discovery_sessions",
    "mcp_connections",
    "execution_runs",
    "approval_actions",
)


class _FakeDB:
    """Returns rows for whichever table a statement selects FROM."""

    def __init__(self, rows=None, get_map=None):
        self.rows = {k: list(v) for k, v in (rows or {}).items()}
        self.get_map = get_map or {}
        self.added = []
        self.deleted = []
        self.committed = 0
        self.next_id = 1000
        self.statements = []

    def _table_for(self, statement: str) -> str | None:
        # Longest name first so automation_suite_test_cases is not matched as
        # automation_suites.
        for table in _TABLES:
            if f" {table}" in statement:
                return table
        return None

    async def execute(self, stmt):
        statement = str(stmt)
        self.statements.append(statement)
        table = self._table_for(statement)
        values = self.rows.get(table, [])
        if "count(" in statement:
            return _ExecuteResult([], scalar=len(values))
        if "sum(" in statement:
            return _ExecuteResult([(0, 0)])
        return _ExecuteResult(values)

    async def get(self, model, ident):
        return self.get_map.get((model.__name__, ident))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        return None

    async def refresh(self, _obj, attribute_names=None):
        return None


def _suite(**overrides):
    defaults = dict(
        id=1,
        project_id=1,
        name="Postpaid Order Provisioning E2E",
        description=None,
        tags=[],
        status="DRAFT",
        version=1,
        is_current=True,
        default_environment="SIT",
        owner_id=3,
        created_by=3,
        correlation_id=None,
        members_total=0,
        members_included=0,
        members_ready=0,
        members_blocked=0,
        members_manual_only=0,
        members_drifted=0,
        gaps_critical_open=0,
        gaps_warning_open=0,
        conflicts_open=0,
        archived_by=None,
        archived_at=None,
        last_evaluated_at=None,
        last_inheritance_sync_at=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _events(db):
    return [a.event_type for a in db.added if hasattr(a, "event_type")]


# ─── Lookups ──────────────────────────────────────────────────────────────────

def test_get_suite_or_404_raises_a_typed_error():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.get_suite_or_404(_FakeDB(), 42)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "SUITE_NOT_FOUND"

    anyio.run(scenario)


# ─── Creation and idempotency ─────────────────────────────────────────────────

def test_a_replayed_idempotency_key_returns_the_same_suite_without_inserting():
    async def scenario():
        existing = _suite(id=7)
        db = _FakeDB(rows={"automation_suites": [existing]})
        suite, created = await svc.create_suite(
            db,
            project_id=1,
            name="Anything",
            description=None,
            tags=[],
            test_case_ids=[10],
            test_suite_ids=[],
            default_environment="SIT",
            idempotency_key="wizard-session-abc",
            actor_id=3,
        )
        assert suite is existing
        assert created is False
        # Nothing was written — no suite row, no membership, no activity.
        assert db.added == []

    anyio.run(scenario)


def test_a_duplicate_active_name_is_rejected():
    async def scenario():
        db = _FakeDB(rows={"automation_suites": [_suite(id=7, name="Retail Onboarding Regression")]})
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.create_suite(
                db,
                project_id=1,
                name="Retail Onboarding Regression",
                description=None,
                tags=[],
                test_case_ids=[],
                test_suite_ids=[],
                default_environment=None,
                idempotency_key=None,
                actor_id=3,
            )
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SUITE_NAME_EXISTS"

    anyio.run(scenario)


def test_a_blank_name_is_rejected():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.create_suite(
                _FakeDB(),
                project_id=1,
                name="   ",
                description=None,
                tags=[],
                test_case_ids=[],
                test_suite_ids=[],
                default_environment=None,
                idempotency_key=None,
                actor_id=3,
            )
        assert exc.value.detail["code"] == "SUITE_NAME_REQUIRED"

    anyio.run(scenario)


def test_creating_a_suite_logs_creation_and_evaluates_it():
    async def scenario():
        db = _FakeDB()
        suite, created = await svc.create_suite(
            db,
            project_id=1,
            name="Billing Validation",
            description="desc",
            tags=["billing"],
            test_case_ids=[],
            test_suite_ids=[],
            default_environment="SIT",
            idempotency_key="key-1",
            actor_id=3,
        )
        assert created is True
        assert isinstance(suite, AutomationSuite)
        assert "suite_created" in _events(db)
        assert "suite_evaluated" in _events(db)
        # No members yet, so the deterministic status is DRAFT.
        assert suite.status == "DRAFT"

    anyio.run(scenario)


# ─── Membership ───────────────────────────────────────────────────────────────

def test_add_members_skips_existing_and_rejects_unknown_test_cases():
    async def scenario():
        suite = _suite()
        db = _FakeDB(
            rows={
                # The service selects the test_case_id column here, not entities.
                "automation_suite_test_cases": [10],
                # 10 and 11 both exist; 99 does not.
                "test_cases": [
                    SimpleNamespace(id=10, project_id=1, is_deleted=False),
                    SimpleNamespace(id=11, project_id=1, is_deleted=False),
                ],
            }
        )
        result = await svc.add_members(db, suite, test_case_ids=[10, 11, 99], actor_id=3, commit=False)
        assert result["added"] == 1
        # 10 is already a member, 99 is not a real test case in this project.
        assert result["skipped_duplicate"] == 1
        assert [r["test_case_id"] for r in result["rejected"]] == [99]
        added_members = [a for a in db.added if isinstance(a, AutomationSuiteTestCase)]
        assert [m.test_case_id for m in added_members] == [11]
        assert "members_added" in _events(db)

    anyio.run(scenario)


def test_add_members_is_a_no_op_when_nothing_is_requested():
    async def scenario():
        db = _FakeDB()
        result = await svc.add_members(db, _suite(), test_case_ids=[], actor_id=3, commit=False)
        assert result == {"added": 0, "skipped_duplicate": 0, "rejected": []}
        assert db.added == []

    anyio.run(scenario)


def test_excluding_a_member_records_who_and_why():
    async def scenario():
        member = AutomationSuiteTestCase(
            id=5, suite_id=1, test_case_id=10, inclusion_status="included", member_status="BLOCKED",
            readiness_checks_passed=0, readiness_checks_total=0, source_test_case_version=0,
        )
        suite = _suite()
        db = _FakeDB(get_map={("AutomationSuiteTestCase", 5): member})
        updated = await svc.update_member(
            db, suite, 5, inclusion_status="excluded", exclusion_reason="Owned by the manual pack", actor_id=3
        )
        assert updated.inclusion_status == "excluded"
        assert updated.excluded_by == 3
        assert updated.exclusion_reason == "Owned by the manual pack"
        assert "member_excluded" in _events(db)

    anyio.run(scenario)


def test_removing_a_member_that_is_not_in_this_suite_404s():
    async def scenario():
        foreign = AutomationSuiteTestCase(id=5, suite_id=999, test_case_id=10)
        db = _FakeDB(get_map={("AutomationSuiteTestCase", 5): foreign})
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.remove_member(db, _suite(), 5, actor_id=3)
        assert exc.value.status_code == 404
        assert exc.value.detail["code"] == "MEMBER_NOT_FOUND"

    anyio.run(scenario)


# ─── Evaluation ───────────────────────────────────────────────────────────────

def test_evaluating_an_empty_suite_writes_the_rollup_and_logs_it():
    async def scenario():
        suite = _suite(members_total=4, members_included=4, gaps_critical_open=2)
        db = _FakeDB()
        result = await svc.evaluate_suite(db, suite, actor_id=3)
        assert result.status == "DRAFT"
        # Stale counters from a previous pass must be cleared, not left behind.
        assert result.members_total == 0
        assert result.members_included == 0
        assert result.gaps_critical_open == 0
        assert result.last_evaluated_at is not None
        assert result.last_inheritance_sync_at is not None
        assert "suite_evaluated" in _events(db)
        assert db.committed >= 1

    anyio.run(scenario)


def test_an_archived_suite_cannot_be_evaluated_or_changed():
    async def scenario():
        archived = _suite(status="ARCHIVED")
        for call in (
            svc.evaluate_suite(_FakeDB(), archived, actor_id=3),
            svc.update_suite(_FakeDB(), archived, name="new", actor_id=3),
        ):
            with pytest.raises(AutomationSuiteError) as exc:
                await call
            assert exc.value.status_code == 409
            assert exc.value.detail["code"] == "SUITE_ARCHIVED"

    anyio.run(scenario)


# ─── Archive ──────────────────────────────────────────────────────────────────

def test_archiving_sets_the_audit_fields():
    async def scenario():
        suite = _suite()
        db = _FakeDB()
        result = await svc.archive_suite(db, suite, actor_id=3)
        assert result.status == "ARCHIVED"
        assert result.is_current is False
        assert result.archived_by == 3
        assert result.archived_at is not None
        assert "suite_archived" in _events(db)

    anyio.run(scenario)


def test_archiving_twice_conflicts():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.archive_suite(_FakeDB(), _suite(status="ARCHIVED"), actor_id=3)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "ALREADY_ARCHIVED"

    anyio.run(scenario)


# ─── Gap adjudication ─────────────────────────────────────────────────────────

def test_a_finding_with_no_grouping_meaning_cannot_be_split():
    """Splitting resolves framework/environment conflicts, nothing else."""

    async def scenario():
        gap = SimpleNamespace(
            id=1, suite_id=1, suite_test_case_id=5, gap_type="TEST_CASE_NOT_APPROVED", status="open",
            resolution_action=None, reviewer_notes=None, resolved_by=None, resolved_at=None, auto_closed=False,
        )
        db = _FakeDB(get_map={("AutomationSuiteGap", 1): gap})
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.resolve_gap(
                db, _suite(), gap_id=1, resolution_action="split_execution_groups", reviewer_notes=None, actor_id=3
            )
        assert exc.value.status_code == 422
        assert exc.value.detail["code"] == "NOT_SPLITTABLE"

    anyio.run(scenario)


def test_approving_an_exception_requires_a_reason():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.approve_exception(_FakeDB(), _suite(), gap_id=1, reason="  ", actor_id=3)
        assert exc.value.detail["code"] == "REASON_REQUIRED"

    anyio.run(scenario)


def test_approving_an_exception_waives_the_gap_and_writes_an_approval_record():
    async def scenario():
        gap = SimpleNamespace(
            id=4, suite_id=1, suite_test_case_id=5, gap_type="LOCATOR_MISSING", status="open",
            resolution_action=None, reviewer_notes=None, resolved_by=None, resolved_at=None, auto_closed=False,
        )
        db = _FakeDB(get_map={("AutomationSuiteGap", 4): gap})
        result = await svc.approve_exception(
            db, _suite(), gap_id=4, reason="Accepted risk for this release", actor_id=3
        )
        assert result.status == "exception_approved"
        assert result.resolution_action == "approve_exception"
        assert result.resolved_by == 3
        assert "exception_approved" in _events(db)
        # Waivers also land in the shared approval ledger.
        approvals = [a for a in db.added if getattr(a, "entity_type", None) == "automation_suite_gap"]
        assert len(approvals) == 1
        assert approvals[0].decision == "approved"
        assert approvals[0].user_id == 3

    anyio.run(scenario)


def test_a_gap_from_another_suite_404s():
    async def scenario():
        foreign = SimpleNamespace(id=4, suite_id=999)
        db = _FakeDB(get_map={("AutomationSuiteGap", 4): foreign})
        with pytest.raises(AutomationSuiteError) as exc:
            await svc.approve_exception(db, _suite(), gap_id=4, reason="why", actor_id=3)
        assert exc.value.detail["code"] == "GAP_NOT_FOUND"

    anyio.run(scenario)
