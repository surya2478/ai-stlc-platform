"""Test Automation Classification & Routing (P1-S3 extension).

Follows the queued-response _FakeDB pattern from
test_project_applications_registry.py — this codebase has no real-DB test
fixture, so async service functions are exercised against a fake session
that replays queued execute()/get() responses in call order.
"""
from datetime import datetime, timezone

import anyio
import pytest
from fastapi import HTTPException

from app.models.automation_classification import AutomationClassificationPolicy, TestCaseAutomationClassification
from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.services.test_classification import (
    capability_resolver,
    classification_service,
    deterministic_rules,
    policy_resolver,
    scoring_service,
)
from app.services.test_classification.policy_defaults import default_policy_rules
from app.services.test_classification.context import ClassificationContext


class _Result:
    def __init__(self, value=None, values=None):
        self._value = value
        self._values = values if values is not None else []

    def scalar(self):
        return self._value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._values

    def first(self):
        return self._values[0] if self._values else None


class _FakeDB:
    def __init__(self, responses=(), gets=None):
        self.responses = list(responses)
        self.gets = gets or {}
        self.added = []

    async def execute(self, _stmt):
        value = self.responses.pop(0)
        if isinstance(value, list):
            return _Result(values=value)
        return _Result(value=value)

    async def get(self, model, pk):
        return self.gets.get((model, pk))

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = len(self.added) + 1
        self.added.append(obj)

    async def flush(self):
        return None

    async def refresh(self, _obj):
        return None


def _policy(id_: int = 1, **overrides) -> AutomationClassificationPolicy:
    data = {
        "id": id_, "project_id": 1, "application_id": None, "code": "WEB_TELECOM_E2E",
        "name": "Web Telecom E2E", "version": 1, "status": "published",
        "rules": {
            "candidate_rules": {
                "block_if": ["unresolved_requirement", "missing_expected_result", "unsupported_application"],
                "conditional_if": ["test_data_not_ready"],
                "minimum_automation_value_score": 60,
            },
            "routing_rules": [{"when": {"channel": "WEB"}, "primary_adapter": "PLAYWRIGHT_MCP"}],
            "external_validation_rules": [{"required": ["OMS_MCP"], "optional": ["CRM_MCP"]}],
        },
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return AutomationClassificationPolicy(**data)


def _requirement(id_: int = 1, **overrides) -> Requirement:
    data = {
        "id": id_, "project_id": 1, "requirement_id": f"REQ-{id_}", "title": "Req",
        "status": "approved", "risk_level": "high", "regulatory_impact": False,
        "revenue_impact": False, "customer_impact": False,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return Requirement(**data)


def _application(id_: int = 1, **overrides) -> ProjectApplication:
    data = {
        "id": id_, "project_id": 1, "key": "web", "name": "Web App", "is_active": True,
        "environment_urls": {}, "is_default": True, "aliases": [], "lifecycle_status": "active",
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return ProjectApplication(**data)


def _test_case(id_: int = 1, **overrides) -> TestCase:
    data = {
        "id": id_, "project_id": 1, "test_case_id": f"TC-{id_}", "title": "Login works",
        "priority": "High", "severity": "High", "test_type": "WEB", "automation_candidate": True,
        "steps": [{"step_number": 1, "action": "Go to login", "expected_result": "Page loads"}],
        "expected_result": "User is logged in", "preconditions": ["User exists"],
        "test_data": {"username": "u"}, "status": "approved", "version": 1,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return TestCase(**data)


def _ctx(**overrides) -> ClassificationContext:
    base = dict(
        test_case=_test_case(), requirement=_requirement(), scenario=None,
        application=_application(), policy=_policy(),
    )
    base.update(overrides)
    return ClassificationContext(**base)


# ── deterministic_rules ──────────────────────────────────────────────────

def test_pre_agent_no_blockers_for_healthy_case():
    result = deterministic_rules.evaluate_pre_agent(_ctx())
    assert result.blockers == []


def test_policy_capability_allowlists_exclude_evidence_keys():
    ctx = _ctx(
        policy=_policy(
            rules={
                "routing_rules": [
                    {
                        "when": {},
                        "primary_adapter": "PLAYWRIGHT_MCP",
                        "supporting_adapters": ["API_ADAPTER"],
                    }
                ],
                "external_validation_rules": [
                    {"required": ["OMS_MCP"], "optional": ["CRM_MCP"]}
                ],
                "evidence_rules": {
                    "web_e2e": {"mandatory": ["SCREENSHOT", "DOM_SNAPSHOT"]}
                },
            }
        )
    )

    adapters, validators = classification_service.policy_capability_allowlists(ctx)

    assert adapters == {"PLAYWRIGHT_MCP", "API_ADAPTER"}
    assert validators == {"OMS_MCP", "CRM_MCP"}
    assert "SCREENSHOT" not in adapters | validators
    assert "DOM_SNAPSHOT" not in adapters | validators


def test_pre_agent_blocks_on_unapproved_requirement():
    ctx = _ctx(requirement=_requirement(status="draft"))
    result = deterministic_rules.evaluate_pre_agent(ctx)
    assert any(f.code == "unresolved_requirement" for f in result.blockers)


def test_pre_agent_blocks_on_missing_application():
    ctx = _ctx(application=None)
    result = deterministic_rules.evaluate_pre_agent(ctx)
    assert any(f.code == "unsupported_application" for f in result.blockers)


def test_pre_agent_conditional_warns_on_missing_test_data():
    ctx = _ctx(test_case=_test_case(test_data=None))
    result = deterministic_rules.evaluate_pre_agent(ctx)
    assert any(f.code == "test_data_not_ready" for f in result.warnings)
    assert result.blockers == []


def test_pre_agent_guardrail_blocks_captcha_regardless_of_policy():
    ctx = _ctx(test_case=_test_case(metadata_={"classification_flags": {"captcha_dependency": True}}))
    result = deterministic_rules.evaluate_pre_agent(ctx)
    assert any(f.code == "manual_only:captcha" for f in result.blockers)


def test_default_manual_only_condition_blocks_atm_test_with_clear_message():
    ctx = _ctx(test_case=_test_case(title="Verify cash withdrawal on an ATM machine"))
    result = deterministic_rules.evaluate_pre_agent(ctx)
    finding = next(item for item in result.blockers if item.code == "manual_only:atm")
    assert finding.label == "Automation not possible: ATM machine"
    assert "physical ATM hardware" in finding.detail
    assert "Matched configured keyword 'atm'" in finding.detail


def test_project_can_define_custom_manual_only_condition():
    policy = _policy(
        rules={
            "manual_only_conditions": [
                {
                    "code": "smart_card_reader",
                    "label": "Physical smart-card reader",
                    "keywords": ["smart card reader"],
                    "reason": "A certified reader and physical card are required.",
                }
            ],
            "candidate_rules": {"block_if": [], "conditional_if": []},
        }
    )
    ctx = _ctx(policy=policy, test_case=_test_case(title="Validate smart card reader authentication"))
    result = deterministic_rules.evaluate_pre_agent(ctx)
    assert [item.code for item in result.blockers] == ["manual_only:smart_card_reader"]


def test_capability_mandatory_gap_always_blocks_even_without_policy_config():
    result = deterministic_rules.evaluate_capability(
        _ctx(), mandatory_unavailable=["BILLING_MCP"], optional_unavailable=[]
    )
    assert any(f.code == "mandatory_validator_not_configured" for f in result.blockers)


# ── scoring_service ───────────────────────────────────────────────────────

def test_scores_are_clamped_0_to_100():
    complexity, automation_value, factors = scoring_service.compute_scores(
        _ctx(), mandatory_validator_count=5, optional_validator_count=5
    )
    assert 0 <= complexity <= 100
    assert 0 <= automation_value <= 100
    assert len(factors) == 9  # 5 automation_value + 4 complexity factors


def test_default_policy_is_safe_and_available_without_environment_flags():
    rules = default_policy_rules()
    candidate = rules["candidate_rules"]
    assert candidate["minimum_automation_value_score"] == 60
    assert "missing_expected_result" in candidate["block_if"]
    assert "unsupported_application" in candidate["conditional_if"]
    assert rules["routing_rules"][0]["primary_adapter"] == "PLAYWRIGHT_MCP"


@pytest.mark.anyio
async def test_publish_project_policy_creates_versioned_project_override():
    previous = _policy(id_=8, project_id=9, version=2)
    db = _FakeDB(responses=[[previous]])
    rules = default_policy_rules()
    rules["candidate_rules"]["minimum_automation_value_score"] = 75

    published = await policy_resolver.publish_project_policy(
        db,
        project_id=9,
        name="Project 9 policy",
        rules=rules,
        user_id=4,
    )

    assert published.project_id == 9
    assert published.version == 3
    assert published.parent_policy_id == 8
    assert published.status == "published"
    assert published.rules["candidate_rules"]["minimum_automation_value_score"] == 75


def test_more_external_dependencies_increase_complexity():
    low, _, _ = scoring_service.compute_scores(_ctx(), mandatory_validator_count=0, optional_validator_count=0)
    high, _, _ = scoring_service.compute_scores(_ctx(), mandatory_validator_count=3, optional_validator_count=3)
    assert high >= low


# ── policy_resolver precedence ───────────────────────────────────────────

def test_resolve_effective_policy_scope_precedence():
    async def _run():
        # policy_resolver._published_at_scope uses .scalars().first(), so a
        # "found" response must be a list (see _FakeDB.execute); a bare None
        # means "not found" either way.

        # Application-scoped published row wins outright.
        app_policy = _policy(id_=2, application_id=5)
        db = _FakeDB(responses=[[app_policy]])
        result = await policy_resolver.resolve_effective_policy(db, project_id=1, application_id=5)
        assert result.id == 2

        # No application-scoped row -> falls through to project-scoped.
        db2 = _FakeDB(responses=[None, [_policy(id_=3)]])
        result2 = await policy_resolver.resolve_effective_policy(db2, project_id=1, application_id=5)
        assert result2.id == 3

        # No application_id requested at all -> project tier is checked first.
        db3 = _FakeDB(responses=[[_policy(id_=4, application_id=None)]])
        result3 = await policy_resolver.resolve_effective_policy(db3, project_id=1, application_id=None)
        assert result3.id == 4

    anyio.run(_run)


def test_resolve_effective_policy_raises_when_none_published():
    async def _run():
        db = _FakeDB(responses=[None, None, None])
        with pytest.raises(HTTPException) as exc_info:
            await policy_resolver.resolve_effective_policy(db, project_id=1, application_id=None)
        assert exc_info.value.status_code == 404
        assert exc_info.value.detail["code"] == "CLASSIFICATION_POLICY_NOT_FOUND"

    anyio.run(_run)


def test_require_published_rejects_draft():
    with pytest.raises(HTTPException) as exc_info:
        policy_resolver.require_published(_policy(status="draft"))
    assert exc_info.value.status_code == 409


# ── capability_resolver ──────────────────────────────────────────────────

def test_unavailable_keys_excludes_real_and_mock():
    resolved = {
        "A": capability_resolver.CapabilityStatus("A", "REAL", 1, "ok"),
        "B": capability_resolver.CapabilityStatus("B", "NOT_CONFIGURED", 2, "not ready"),
        "C": capability_resolver.CapabilityStatus("C", "UNSUPPORTED", None, "unknown"),
    }
    assert capability_resolver.unavailable_keys(resolved) == ["B", "C"]


# ── classification_service.decide_classification ────────────────────────

def _classification(id_: int = 1, **overrides) -> TestCaseAutomationClassification:
    data = {
        "id": id_, "project_id": 1, "test_case_id": 1, "test_case_version": 1, "version": 1,
        "is_current": True, "candidate_status": "RECOMMENDED",
        "supporting_adapters": [], "mandatory_validators": [], "optional_validators": [],
        "discovery_required": False, "score_factors": [], "required_evidence": [],
        "required_capabilities": [], "deterministic_blockers": [], "advisory_warnings": [],
        "matched_rules": [], "policy_id": 1, "policy_version": 1,
        "review_status": "PENDING_REVIEW", "reviewed_by": None,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
        "updated_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }
    data.update(overrides)
    return TestCaseAutomationClassification(**data)


def test_decide_rejects_missing_reason_for_conditional():
    async def _run():
        row = _classification()
        with pytest.raises(HTTPException) as exc_info:
            await classification_service.decide_classification(
                _FakeDB(), classification=row, decision="approve_conditional", user_id=1,
                reason=None, actor_role="QA Manager", allow_self_review_override=True,
            )
        assert exc_info.value.status_code == 422

    anyio.run(_run)


def test_decide_rejects_self_review_without_override():
    async def _run():
        row = _classification(reviewed_by=7)
        with pytest.raises(HTTPException) as exc_info:
            await classification_service.decide_classification(
                _FakeDB(), classification=row, decision="approve", user_id=7,
                reason=None, actor_role="QA Manager", allow_self_review_override=False,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "SEPARATION_OF_DUTY_VIOLATION"

    anyio.run(_run)


def test_decide_approve_blocks_on_stale_test_case_version():
    async def _run():
        row = _classification(test_case_version=1)
        db = _FakeDB(gets={(TestCase, 1): _test_case(version=2)})
        with pytest.raises(HTTPException) as exc_info:
            await classification_service.decide_classification(
                db, classification=row, decision="approve", user_id=9,
                reason=None, actor_role="QA Manager", allow_self_review_override=True,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "TEST_CASE_VERSION_STALE"

    anyio.run(_run)


def test_decide_approve_blocks_when_deterministic_blockers_present():
    async def _run():
        row = _classification(deterministic_blockers=[{"code": "x", "label": "x", "detail": "x"}])
        db = _FakeDB(
            responses=[[_policy(id_=1)]],
            gets={(TestCase, 1): _test_case(version=1)},
        )
        with pytest.raises(HTTPException) as exc_info:
            await classification_service.decide_classification(
                db, classification=row, decision="approve", user_id=9,
                reason=None, actor_role="QA Manager", allow_self_review_override=True,
            )
        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["code"] == "TEST_CASE_NOT_ELIGIBLE"

    anyio.run(_run)


def test_decide_approve_succeeds_and_sets_immutable_fields():
    async def _run():
        row = _classification()
        db = _FakeDB(
            responses=[[_policy(id_=1, version=1)]],
            gets={(TestCase, 1): _test_case(version=1)},
        )
        updated = await classification_service.decide_classification(
            db, classification=row, decision="approve", user_id=9,
            reason=None, actor_role="QA Manager", allow_self_review_override=True,
        )
        assert updated.candidate_status == "APPROVED"
        assert updated.review_status == "APPROVED"
        assert updated.approved_by == 9
        assert updated.approved_at is not None

    anyio.run(_run)


def test_approving_a_classification_makes_the_test_case_automatable():
    """The decision has to land where the rest of the platform reads it.

    AI Automation Studio selects on execution_mode + automation_eligible
    (test_plan_service.list_test_cases). Approval used to write only the
    classification row, so a test case could read "APPROVED · PLAYWRIGHT_MCP"
    on its AI Info tab and never once appear in the studio.
    """
    async def _run():
        test_case = _test_case(version=1, execution_mode="manual", automation_eligible="no",
                               automation_status="not_required")
        db = _FakeDB(
            responses=[[_policy(id_=1, version=1)]],
            gets={(TestCase, 1): test_case},
        )
        await classification_service.decide_classification(
            db, classification=_classification(), decision="approve", user_id=9,
            reason=None, actor_role="QA Manager", allow_self_review_override=True,
        )

        assert test_case.execution_mode == "automation"
        assert test_case.automation_eligible == "yes"
        assert test_case.automation_status == "ready_for_automation"

    anyio.run(_run)


def test_execution_mode_moves_off_manual_so_the_next_edit_cannot_undo_it():
    """Not cosmetic: `_normalize_automation_update` rewrites
    automation_eligible to "no" whenever execution_mode is "manual" and *any*
    field is updated. Observed on TC-0102, whose "yes" verdict was wiped in the
    same transaction that merely mapped it to an application. Leaving the mode
    alone would make this write-back last exactly until the next edit."""
    async def _run():
        from app.schemas.test_plan import TestCaseUpdate
        from app.services import test_plan_service

        test_case = _test_case(version=1, execution_mode="manual", automation_eligible="no",
                               automation_status="not_required")
        db = _FakeDB(
            responses=[[_policy(id_=1, version=1)]],
            gets={(TestCase, 1): test_case},
        )
        await classification_service.decide_classification(
            db, classification=_classification(), decision="approve", user_id=9,
            reason=None, actor_role="QA Manager", allow_self_review_override=True,
        )

        # Any unrelated later edit runs the same normalisation that wiped
        # TC-0102 when its only change was an application mapping.
        await test_plan_service.update_test_case(
            db, test_case, TestCaseUpdate(priority="Medium"), user_id=9,
        )
        assert test_case.automation_eligible == "yes"
        assert test_case.execution_mode == "automation"

    anyio.run(_run)


def test_apply_review_corrections_rejects_already_approved():
    async def _run():
        row = _classification(review_status="APPROVED")
        with pytest.raises(HTTPException) as exc_info:
            await classification_service.apply_review_corrections(
                _FakeDB(), classification=row, corrections={"primary_adapter": "SELENIUM"},
                user_id=1, reason="correction",
            )
        assert exc_info.value.status_code == 409

    anyio.run(_run)


def test_apply_review_corrections_records_field_correction():
    async def _run():
        row = _classification(primary_adapter="PLAYWRIGHT_MCP")
        db = _FakeDB()
        updated = await classification_service.apply_review_corrections(
            db, classification=row, corrections={"primary_adapter": "SELENIUM"}, user_id=3, reason="better fit",
        )
        assert updated.primary_adapter == "SELENIUM"
        assert updated.review_status == "REVIEWED"
        assert updated.reviewed_by == 3
        assert len(db.added) == 1
        assert db.added[0].field_name == "primary_adapter"
        assert db.added[0].ai_value == "PLAYWRIGHT_MCP"
        assert db.added[0].reviewer_value == "SELENIUM"

    anyio.run(_run)
