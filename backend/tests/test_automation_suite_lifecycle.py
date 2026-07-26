"""Approval workflow, publication snapshots, versions and impact review.

The rules asserted here are the governance guarantees: a suite cannot skip
review states, the submitter cannot clear their own work, publication freezes an
immutable snapshot, and a source changing afterwards produces a finding rather
than rewriting what was published.
"""
from types import SimpleNamespace

import anyio
import pytest

from app.models.automation_suite import AutomationSuite, AutomationSuiteSnapshot, AutomationSuiteTestCase
from app.services.automation_suite import lifecycle
from app.services.automation_suite.errors import AutomationSuiteError
from app.services.automation_suite.inheritance import MemberInheritance, SuiteInheritance


class _Result:
    def __init__(self, values, scalar=None):
        self._values = list(values)
        self._scalar = scalar

    def scalars(self):
        return self

    def all(self):
        return list(self._values)

    def first(self):
        return self._values[0] if self._values else None

    def scalar(self):
        return self._scalar if self._scalar is not None else len(self._values)


_TABLES = (
    "automation_suite_test_cases",
    "automation_suite_execution_groups",
    "automation_suite_snapshots",
    "automation_suite_activity",
    "automation_suite_gaps",
    "automation_suites",
    "test_cases",
    "approval_actions",
)


class _FakeDB:
    def __init__(self, rows=None):
        self.rows = {k: list(v) for k, v in (rows or {}).items()}
        self.added = []
        self.committed = 0

    async def execute(self, stmt):
        statement = str(stmt)
        for table in _TABLES:
            if f" {table}" in statement:
                return _Result(self.rows.get(table, []))
        return _Result([])

    async def get(self, model, ident):
        return None

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = 500 + len(self.added)
        self.added.append(obj)

    async def delete(self, obj):
        pass

    async def flush(self):
        pass

    async def commit(self):
        self.committed += 1

    async def rollback(self):
        pass

    async def refresh(self, _obj, attribute_names=None):
        pass


def _suite(**overrides):
    defaults = dict(
        id=1,
        project_id=1,
        name="Postpaid Order Provisioning E2E",
        description=None,
        tags=[],
        status="READY_FOR_VALIDATION",
        version=1,
        parent_suite_id=None,
        is_current=True,
        default_environment="SIT",
        owner_id=3,
        created_by=3,
        correlation_id=None,
        members_included=2,
        submitted_by=None,
        submitted_at=None,
        reviewed_by=None,
        reviewed_at=None,
        approved_by=None,
        approved_at=None,
        published_by=None,
        published_at=None,
        decision_reason=None,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _member_row(member_id=1, test_case_id=10):
    return SimpleNamespace(
        id=member_id,
        suite_id=1,
        test_case_id=test_case_id,
        inclusion_status="included",
        planned_sequence=None,
        source_system="platform",
        source_reference=None,
        execution_group_id=None,
        # Read by the inheritance resolver when publish freezes the scope.
        last_evaluated_at=None,
        source_test_case_version=0,
        resolved_classification_id=None,
        resolved_application_id=None,
        resolved_model_id=None,
    )


def _events(db):
    return [a.event_type for a in db.added if hasattr(a, "event_type")]


def _approvals(db):
    return [a for a in db.added if getattr(a, "entity_type", None) == "automation_suite"]


# ─── Submit ───────────────────────────────────────────────────────────────────

def test_cannot_submit_a_draft_for_review():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.submit_for_review(_FakeDB(), _suite(status="DRAFT"), actor_id=3)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "INVALID_TRANSITION"

    anyio.run(scenario)


def test_cannot_submit_while_critical_findings_are_open():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_gaps": [SimpleNamespace(id=1, severity="critical", status="open")]})
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.submit_for_review(db, _suite(), actor_id=3)
        assert exc.value.detail["code"] == "CRITICAL_GAP_OPEN"

    anyio.run(scenario)


def test_cannot_submit_a_suite_with_no_members():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_test_cases": []})
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.submit_for_review(db, _suite(), actor_id=3)
        assert exc.value.detail["code"] == "NO_MEMBERS"

    anyio.run(scenario)


def test_submitting_records_who_and_when():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_test_cases": [_member_row()]})
        suite = _suite()
        result = await lifecycle.submit_for_review(db, suite, actor_id=3)
        assert result.status == "READY_FOR_REVIEW"
        assert result.submitted_by == 3
        assert result.submitted_at is not None
        assert "submitted_for_review" in _events(db)

    anyio.run(scenario)


# ─── Review decisions ─────────────────────────────────────────────────────────

def test_requesting_changes_needs_a_reason_and_returns_control_to_the_engine():
    async def scenario():
        db = _FakeDB()
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.request_changes(db, _suite(status="READY_FOR_REVIEW"), actor_id=4, reason=" ")
        assert exc.value.detail["code"] == "REASON_REQUIRED"

        suite = _suite(status="READY_FOR_REVIEW")
        result = await lifecycle.request_changes(db, suite, actor_id=4, reason="Split the frameworks first")
        # Back to a derived status so the next evaluation owns it again.
        assert result.status == "READY_FOR_VALIDATION"
        assert result.reviewed_by == 4
        assert result.decision_reason == "Split the frameworks first"

    anyio.run(scenario)


def test_rejecting_records_an_approval_ledger_entry():
    async def scenario():
        db = _FakeDB()
        result = await lifecycle.reject(db, _suite(status="READY_FOR_REVIEW"), actor_id=4, reason="Wrong scope")
        assert result.status == "READY_FOR_VALIDATION"
        ledger = _approvals(db)
        assert len(ledger) == 1
        assert ledger[0].decision == "rejected"
        assert ledger[0].user_id == 4

    anyio.run(scenario)


def test_only_a_suite_awaiting_review_can_be_approved():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.approve(_FakeDB(), _suite(status="READY_FOR_VALIDATION"), actor_id=4)
        assert exc.value.detail["code"] == "INVALID_TRANSITION"

    anyio.run(scenario)


def test_the_submitter_cannot_approve_their_own_suite():
    async def scenario():
        suite = _suite(status="READY_FOR_REVIEW", submitted_by=3)
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.approve(_FakeDB(), suite, actor_id=3)
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "SEPARATION_OF_DUTY_VIOLATION"

    anyio.run(scenario)


def test_a_second_user_can_approve_and_it_is_recorded():
    async def scenario():
        db = _FakeDB()
        suite = _suite(status="READY_FOR_REVIEW", submitted_by=3)
        result = await lifecycle.approve(db, suite, actor_id=4, reason="Scope verified")
        assert result.status == "APPROVED"
        assert result.approved_by == 4
        assert result.approved_at is not None
        assert _approvals(db)[0].decision == "approved"
        assert "approved" in _events(db)

    anyio.run(scenario)


def test_approval_is_blocked_by_open_criticals():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_gaps": [SimpleNamespace(id=1, severity="critical", status="open")]})
        suite = _suite(status="READY_FOR_REVIEW", submitted_by=3)
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.approve(db, suite, actor_id=4)
        assert exc.value.detail["code"] == "CRITICAL_GAP_OPEN"

    anyio.run(scenario)


# ─── Publication and snapshots ────────────────────────────────────────────────

def test_only_an_approved_suite_can_be_published():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.publish(_FakeDB(), _suite(status="READY_FOR_REVIEW"), actor_id=5)
        assert exc.value.detail["code"] == "INVALID_TRANSITION"

    anyio.run(scenario)


def test_publishing_writes_an_immutable_snapshot():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_test_cases": [_member_row()]})
        suite = _suite(status="APPROVED", submitted_by=3, approved_by=4)
        result = await lifecycle.publish(db, suite, actor_id=5)

        assert result.status == "PUBLISHED"
        assert result.published_by == 5
        assert result.published_at is not None

        snapshots = [a for a in db.added if isinstance(a, AutomationSuiteSnapshot)]
        assert len(snapshots) == 1
        assert snapshots[0].suite_version == suite.version
        assert len(snapshots[0].checksum) == 64
        assert "published" in _events(db)

    anyio.run(scenario)


def _inh_member(member_id=1, *, tc_version=3, script_version=1, framework="playwright", environment="SIT",
                model_id=9, test_case_id=10):
    script = (
        SimpleNamespace(id=11, framework=framework, status="approved", version=script_version)
        if framework
        else None
    )
    return MemberInheritance(
        member=SimpleNamespace(
            id=member_id, test_case_id=test_case_id, inclusion_status="included", last_evaluated_at=None,
            source_test_case_version=0, resolved_classification_id=None, resolved_application_id=None,
            resolved_model_id=None, execution_group_id=None, planned_sequence=None,
        ),
        test_case=SimpleNamespace(id=test_case_id, status="approved", version=tc_version, is_deleted=False,
                                  execution_mode="automation"),
        application=SimpleNamespace(id=5, key="crm", name="CRM", lifecycle_status="active", environment_urls={}),
        classification=SimpleNamespace(id=7),
        model=SimpleNamespace(id=model_id, status="approved", version=2) if model_id else None,
        model_is_stale=False,
        open_model_gaps=[],
        scripts=[script] if script else [],
        current_scripts=[script] if script else [],
        frameworks=frozenset([framework]) if framework else frozenset(),
        test_data=[],
        recordings=[],
        resolved_environment=environment,
        environment_source="suite_default",
        mandatory_capability_keys=(),
        drift_reasons=(),
    )


def test_the_snapshot_payload_is_deterministic_and_records_source_versions():
    members = [_inh_member(2), _inh_member(1)]
    payload_a, checksum_a = lifecycle.build_snapshot_payload(SuiteInheritance(members=members))
    payload_b, checksum_b = lifecycle.build_snapshot_payload(SuiteInheritance(members=list(reversed(members))))

    # Member order must not change the checksum.
    assert checksum_a == checksum_b
    assert [r["member_id"] for r in payload_a] == [1, 2]
    assert payload_a[0]["test_case_version"] == 3
    assert payload_a[0]["script_version"] == 1
    assert payload_a[0]["framework"] == "playwright"
    assert payload_a[0]["environment"] == "SIT"


def test_the_snapshot_omits_excluded_members():
    excluded = _inh_member(2)
    excluded.member.inclusion_status = "excluded"
    payload, _ = lifecycle.build_snapshot_payload(SuiteInheritance(members=[_inh_member(1), excluded]))
    assert [r["member_id"] for r in payload] == [1]


# ─── Versions ─────────────────────────────────────────────────────────────────

def test_a_new_version_cannot_be_started_from_a_draft():
    async def scenario():
        with pytest.raises(AutomationSuiteError) as exc:
            await lifecycle.create_new_draft(_FakeDB(), _suite(status="DRAFT"), actor_id=3)
        assert exc.value.detail["code"] == "INVALID_TRANSITION"

    anyio.run(scenario)


def test_a_new_version_copies_members_and_supersedes_the_published_one():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_test_cases": [_member_row(1, 10), _member_row(2, 11)]})
        published = _suite(status="PUBLISHED", version=1, published_by=5)
        new_suite = await lifecycle.create_new_draft(db, published, actor_id=3)

        assert new_suite.version == 2
        assert new_suite.status == "DRAFT"
        assert new_suite.parent_suite_id == published.id
        # The published version stays queryable but is no longer current.
        assert published.is_current is False
        copied = [a for a in db.added if isinstance(a, AutomationSuiteTestCase)]
        assert sorted(m.test_case_id for m in copied) == [10, 11]
        assert "new_version_created" in _events(db)

    anyio.run(scenario)


def test_a_second_version_keeps_pointing_at_the_chain_root():
    async def scenario():
        db = _FakeDB(rows={"automation_suite_test_cases": []})
        v2 = _suite(id=2, status="PUBLISHED", version=2, parent_suite_id=1)
        v3 = await lifecycle.create_new_draft(db, v2, actor_id=3)
        assert v3.version == 3
        assert v3.parent_suite_id == 1

    anyio.run(scenario)


# ─── Impact review ────────────────────────────────────────────────────────────

def test_impact_review_reports_nothing_without_a_snapshot():
    async def scenario():
        findings, summary = await lifecycle.detect_snapshot_drift(_FakeDB(), _suite(status="PUBLISHED"))
        assert findings == []
        assert summary["snapshot"] is None

    anyio.run(scenario)


def test_impact_review_flags_a_changed_test_case_version_without_touching_the_snapshot():
    async def scenario():
        frozen = SimpleNamespace(
            id=1,
            suite_id=1,
            suite_version=1,
            checksum="abc",
            created_at=None,
            members=[
                {
                    "member_id": 1,
                    "test_case_id": 10,
                    "test_case_version": 3,
                    "application_model_id": 9,
                    "script_version": 1,
                    "framework": "playwright",
                    "environment": "SIT",
                }
            ],
        )

        # The live test case has moved on to version 4.
        live = _inh_member(1, tc_version=4)

        class _DriftDB(_FakeDB):
            async def execute(self, stmt):
                statement = str(stmt)
                if " automation_suite_snapshots" in statement:
                    return _Result([frozen])
                if " automation_suite_test_cases" in statement:
                    return _Result([live.member])
                return _Result([])

        db = _DriftDB()

        async def _fake_resolve(_db, *, suite, members):
            return SuiteInheritance(members=[live])

        original = lifecycle.inheritance_engine.resolve_suite_inheritance
        lifecycle.inheritance_engine.resolve_suite_inheritance = _fake_resolve
        try:
            findings, summary = await lifecycle.detect_snapshot_drift(db, _suite(status="PUBLISHED"))
        finally:
            lifecycle.inheritance_engine.resolve_suite_inheritance = original

        assert len(findings) == 1
        assert findings[0].gap_type == "SNAPSHOT_DRIFT"
        assert findings[0].severity == "warning"
        assert "changed from 3 to 4" in findings[0].reason
        assert summary["impact_review_required"] is True
        # The snapshot itself is untouched — drift is reported, never applied.
        assert frozen.members[0]["test_case_version"] == 3
        assert frozen.checksum == "abc"

    anyio.run(scenario)


def test_impact_review_is_quiet_when_nothing_moved():
    async def scenario():
        live = _inh_member(1, tc_version=3, script_version=1)
        frozen = SimpleNamespace(
            id=1, suite_id=1, suite_version=1, checksum="abc", created_at=None,
            members=[
                {
                    "member_id": 1, "test_case_id": 10, "test_case_version": 3,
                    "application_model_id": 9, "script_version": 1,
                    "framework": "playwright", "environment": "SIT",
                }
            ],
        )

        class _StableDB(_FakeDB):
            async def execute(self, stmt):
                if " automation_suite_snapshots" in str(stmt):
                    return _Result([frozen])
                return _Result([live.member])

        async def _fake_resolve(_db, *, suite, members):
            return SuiteInheritance(members=[live])

        original = lifecycle.inheritance_engine.resolve_suite_inheritance
        lifecycle.inheritance_engine.resolve_suite_inheritance = _fake_resolve
        try:
            findings, summary = await lifecycle.detect_snapshot_drift(_StableDB(), _suite(status="PUBLISHED"))
        finally:
            lifecycle.inheritance_engine.resolve_suite_inheritance = original

        assert findings == []
        assert summary["impact_review_required"] is False

    anyio.run(scenario)
