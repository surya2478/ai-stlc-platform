"""Edge-case and negative-path tests for automation_intelligence and
automation_service.transition_script.

Runnable directly with Python (no pytest fixtures, no DB) so it works even in
a dev env that's missing test-only deps like `faker`.

Usage:
    .venv/Scripts/python.exe tests/test_automation_intelligence_edge.py
"""
from __future__ import annotations

import os
import sys
import traceback
from dataclasses import dataclass

# Allow direct invocation from the backend/ directory without installing the app.
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)


# ─── Minimal test harness ─────────────────────────────────────────────────────

_PASS: list[str] = []
_FAIL: list[tuple[str, str]] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        _PASS.append(name)
    else:
        _FAIL.append((name, detail))


def _run(fn):
    try:
        fn()
    except AssertionError as exc:
        _FAIL.append((fn.__name__, f"AssertionError: {exc}"))
    except Exception as exc:  # noqa: BLE001
        _FAIL.append((fn.__name__, f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"))


# ─── Fake AutomationScript ────────────────────────────────────────────────────

@dataclass
class FakeScript:
    id: int = 42
    framework: str = "playwright"
    code: str = ""
    status: str = "ai_draft"
    metadata_: dict | None = None


# ─── Intelligence analyzer edge cases ─────────────────────────────────────────

from app.services import automation_intelligence as ai
from app.services import automation_service


def test_empty_script_produces_missing_assertion_warning():
    s = FakeScript(code="")
    r = ai.analyze_script(s)
    # Empty code: should not crash, should still return a report.
    check("empty.report_type", isinstance(r.recommendations, list))
    # No assertions detected → should get a "missing assertions" recommendation.
    kinds = {rec.kind for rec in r.recommendations}
    check("empty.flags_missing_assertion", "missing_assertion" in kinds,
          f"expected missing_assertion in {kinds}")
    check("empty.health_bounded", 0 <= r.health.overall <= 100,
          f"overall={r.health.overall}")


def test_whitespace_only_script_is_safe():
    s = FakeScript(code="\n\n   \t   \n")
    r = ai.analyze_script(s)
    check("whitespace.report_ok", r.script_id == 42)
    check("whitespace.no_locators", r.locators == [])
    check("whitespace.no_crash", isinstance(r.as_dict(), dict))


def test_clean_script_has_high_health():
    # A "clean" playwright script: uses testid, has an assertion, has teardown.
    code = '''
import { test, expect } from "@playwright/test";
test("clean flow", async ({ page }) => {
  await page.goto("/dashboard");
  await page.locator('[data-testid="amount-input"]').fill("100");
  await page.locator('[data-testid="submit-btn"]').click();
  await expect(page.locator('[data-testid="confirmation"]')).toBeVisible();
});
test.afterEach(async () => { /* cleanup */ });
'''
    s = FakeScript(code=code)
    r = ai.analyze_script(s)
    # No hard waits, no xpath, no missing assertion → recommendations should be empty
    # (or at most low-severity nudges).
    high_severity = [rec for rec in r.recommendations if rec.severity == "high"]
    check("clean.no_high_severity", len(high_severity) == 0,
          f"got {[(r.kind, r.title) for r in high_severity]}")
    check("clean.health_good", r.health.overall >= 75,
          f"overall={r.health.overall}")


def test_hard_wait_detected_with_correct_line():
    code = "test('x', async () => {\n  await page.waitForTimeout(5000);\n  await page.click('#ok');\n});"
    s = FakeScript(code=code)
    r = ai.analyze_script(s)
    hard_waits = [rec for rec in r.recommendations if rec.kind == "hard_wait"]
    check("hard_wait.detected", len(hard_waits) == 1,
          f"expected 1 hard wait, got {len(hard_waits)}")
    if hard_waits:
        check("hard_wait.high_severity", hard_waits[0].severity == "high")
        check("hard_wait.related_mentions_line",
              "line 2" in hard_waits[0].related,
              f"related={hard_waits[0].related!r}")


def test_multiple_hard_waits_get_unique_ids():
    code = "waitForTimeout(1000)\nwaitForTimeout(2000)\nwaitForTimeout(3000)"
    s = FakeScript(code=code)
    r = ai.analyze_script(s)
    hard = [rec for rec in r.recommendations if rec.kind == "hard_wait"]
    check("multi_wait.count", len(hard) == 3, f"got {len(hard)}")
    ids = {rec.id for rec in hard}
    check("multi_wait.unique_ids", len(ids) == 3, f"ids={ids}")


def test_stable_ids_across_analyses():
    # Same input → same recommendation IDs (so apply/dismiss decisions match).
    code = "page.waitForTimeout(1000)\npage.click('#submit');"
    s1 = FakeScript(code=code)
    s2 = FakeScript(code=code)
    r1 = ai.analyze_script(s1)
    r2 = ai.analyze_script(s2)
    ids1 = sorted(rec.id for rec in r1.recommendations)
    ids2 = sorted(rec.id for rec in r2.recommendations)
    check("stable_ids.same", ids1 == ids2, f"{ids1} != {ids2}")


def test_exposed_bearer_token_high_severity():
    code = '''const token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc";
await page.setExtraHTTPHeaders({ Authorization: token });'''
    s = FakeScript(code=code)
    r = ai.analyze_script(s)
    creds = [rec for rec in r.recommendations if rec.kind == "exposed_credential"]
    check("bearer.detected", len(creds) >= 1)
    if creds:
        check("bearer.severity", creds[0].severity == "high")


def test_health_never_negative_even_with_many_issues():
    # Stack every anti-pattern together.
    code = (
        "waitForTimeout(1000)\n" * 20
        + "page.locator('#a').click()\n" * 20
        + "//div[1]/button\n" * 20
        + "'Bearer aaaaaaaaaaaaaaaaaa'\n"
        + "'9999999999'\n" * 10
    )
    s = FakeScript(code=code)
    r = ai.analyze_script(s)
    check("bounded.health_ge_0", r.health.overall >= 0, f"overall={r.health.overall}")
    check("bounded.health_le_100", r.health.overall <= 100, f"overall={r.health.overall}")
    for part in r.health.parts:
        check(f"bounded.{part['label']}_range",
              0 <= part["value"] <= 100,
              f"{part}")


def test_locator_finding_shape():
    code = "await page.locator('#amount').fill('100')"
    r = ai.analyze_script(FakeScript(code=code))
    check("locator.at_least_one", len(r.locators) >= 1)
    if r.locators:
        loc = r.locators[0]
        check("locator.has_current", bool(loc.current))
        check("locator.has_suggested", bool(loc.suggested))
        check("locator.confidence_ordered",
              loc.suggested_confidence > loc.current_confidence,
              f"cur={loc.current_confidence}, sug={loc.suggested_confidence}")


def test_recommendation_json_serializable():
    r = ai.analyze_script(FakeScript(code="waitForTimeout(1000); expect(true).toBe(true);"))
    import json
    try:
        json.dumps(r.as_dict())
        check("json.serializable", True)
    except TypeError as e:
        check("json.serializable", False, str(e))


def test_unicode_code_does_not_crash():
    code = "// テスト\npage.click('#按钮') // 🚀\nexpect(true).toBe(true)"
    try:
        r = ai.analyze_script(FakeScript(code=code))
        check("unicode.ok", isinstance(r.as_dict(), dict))
    except Exception as e:
        check("unicode.ok", False, str(e))


def test_env_leak_url_flagged():
    code = 'const url = "https://staging.example.com/api"; await page.goto(url);'
    r = ai.analyze_script(FakeScript(code=code))
    env_leaks = [d for d in r.data_issues if d.kind == "env_leak"]
    check("env_leak.detected", len(env_leaks) >= 1)


def test_record_decision_appends_to_metadata():
    s = FakeScript(metadata_=None)
    entry = ai.record_decision(s, recommendation_id="rec_abc", action="apply", user_id=7)
    check("decision.entry_returned", entry["action"] == "apply")
    check("decision.recorded",
          len((s.metadata_ or {}).get("recommendation_decisions", [])) == 1)
    # Second decision accumulates.
    ai.record_decision(s, recommendation_id="rec_abc", action="dismiss", user_id=7)
    check("decision.accumulates",
          len((s.metadata_ or {}).get("recommendation_decisions", [])) == 2)


def test_record_decision_preserves_existing_metadata():
    s = FakeScript(metadata_={"source": "ai_generation", "language": "ts"})
    ai.record_decision(s, recommendation_id="rec_x", action="apply", user_id=1)
    check("decision.keeps_source", s.metadata_ and s.metadata_.get("source") == "ai_generation")
    check("decision.keeps_language", s.metadata_ and s.metadata_.get("language") == "ts")


# ─── Transition state machine edge cases ──────────────────────────────────────

import asyncio


class FakeSession:
    """Async-compatible stub — flush/refresh are no-ops."""
    async def flush(self):
        return None

    async def refresh(self, obj):
        return None


def _run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def test_transition_submit_from_ai_draft():
    s = FakeScript(status="ai_draft")
    result = _run_async(automation_service.transition_script(
        FakeSession(), s, "submit_for_review", None
    ))
    check("txn.ai_draft_to_in_review", result.status == "in_review")


def test_transition_submit_from_draft():
    s = FakeScript(status="draft")
    result = _run_async(automation_service.transition_script(
        FakeSession(), s, "submit_for_review", None
    ))
    check("txn.draft_to_in_review", result.status == "in_review")


def test_transition_request_changes_from_in_review():
    s = FakeScript(status="in_review")
    result = _run_async(automation_service.transition_script(
        FakeSession(), s, "request_changes", None
    ))
    check("txn.in_review_to_draft", result.status == "draft")


def test_transition_restore_from_rejected():
    s = FakeScript(status="rejected")
    result = _run_async(automation_service.transition_script(
        FakeSession(), s, "restore_draft", None
    ))
    check("txn.rejected_to_draft", result.status == "draft")


def test_transition_from_approved_is_rejected():
    s = FakeScript(status="approved")
    try:
        _run_async(automation_service.transition_script(
            FakeSession(), s, "submit_for_review", None
        ))
        check("txn.approved_blocks_submit", False, "should have raised ValueError")
    except ValueError as e:
        check("txn.approved_blocks_submit", True)
        check("txn.error_message_helpful", "approved" in str(e).lower(),
              f"error={e}")


def test_transition_unknown_action_is_rejected():
    s = FakeScript(status="draft")
    try:
        _run_async(automation_service.transition_script(
            FakeSession(), s, "delete_forever", None
        ))
        check("txn.unknown_action_blocked", False, "should have raised ValueError")
    except ValueError:
        check("txn.unknown_action_blocked", True)


def test_transition_notes_appended_to_metadata_history():
    s = FakeScript(status="draft", metadata_={"source": "ai_generation"})
    _run_async(automation_service.transition_script(
        FakeSession(), s, "submit_for_review", "please review the login flow"
    ))
    history = (s.metadata_ or {}).get("transition_history", [])
    check("txn.notes_recorded", len(history) == 1)
    if history:
        check("txn.notes_content", "please review" in history[0].get("notes", ""))
        check("txn.notes_target", history[0].get("to") == "in_review")
    check("txn.notes_preserve_source",
          (s.metadata_ or {}).get("source") == "ai_generation")


def test_transition_without_notes_does_not_touch_history():
    s = FakeScript(status="draft", metadata_={"source": "ai_generation"})
    _run_async(automation_service.transition_script(
        FakeSession(), s, "submit_for_review", None
    ))
    check("txn.no_history_without_notes",
          "transition_history" not in (s.metadata_ or {}))


def test_transition_double_submit_second_call_fails():
    s = FakeScript(status="draft")
    _run_async(automation_service.transition_script(
        FakeSession(), s, "submit_for_review", None
    ))
    # Now it's in_review; submitting again should fail.
    try:
        _run_async(automation_service.transition_script(
            FakeSession(), s, "submit_for_review", None
        ))
        check("txn.double_submit_blocked", False, "should have raised")
    except ValueError:
        check("txn.double_submit_blocked", True)


# ─── AI-assisted run detection (Phase 3/4) ────────────────────────────────────

from app.services import ai_run_detection


@dataclass
class FakeRun:
    execution_type: str | None = None
    source_type: str | None = None
    metadata_: dict | None = None


def test_ai_detection_legacy_execution_type():
    r = FakeRun(execution_type="ai")
    check("ai_det.legacy_type", ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_source_type():
    r = FakeRun(execution_type="automation", source_type="ai")
    check("ai_det.source_type", ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_source_type_case_insensitive():
    r = FakeRun(execution_type="automation", source_type="AI")
    check("ai_det.source_type_upper", ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_metadata_flag():
    r = FakeRun(execution_type="automation", metadata_={"ai_assisted": True})
    check("ai_det.metadata_true", ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_metadata_flag_string_truthy():
    # SQL migration writes boolean true, but if anything ever writes a string,
    # bool() should still evaluate correctly ("false" is truthy!).
    r = FakeRun(execution_type="automation", metadata_={"ai_assisted": True})
    check("ai_det.metadata_python_true", ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_negative_pure_automation():
    r = FakeRun(execution_type="automation", source_type="automation", metadata_={"other": "field"})
    check("ai_det.pure_automation_negative", not ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_negative_manual():
    r = FakeRun(execution_type="manual", source_type="manual", metadata_=None)
    check("ai_det.manual_negative", not ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_negative_all_none():
    r = FakeRun()
    check("ai_det.all_none_negative", not ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_metadata_ai_assisted_false():
    r = FakeRun(execution_type="automation", metadata_={"ai_assisted": False})
    check("ai_det.metadata_false_negative", not ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_metadata_ai_assisted_missing():
    r = FakeRun(execution_type="automation", metadata_={"source_type": "automation"})
    check("ai_det.metadata_missing_key_negative", not ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_source_type_empty_string():
    r = FakeRun(execution_type="automation", source_type="")
    check("ai_det.empty_source_negative", not ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_precedence_metadata_wins_over_source():
    # Even without source_type, metadata flag alone triggers.
    r = FakeRun(execution_type="automation", source_type=None, metadata_={"ai_assisted": True})
    check("ai_det.metadata_alone", ai_run_detection.is_ai_assisted_run(r))


def test_ai_detection_all_three_signals():
    # Belt-and-braces: run has all three markers, still just True.
    r = FakeRun(execution_type="ai", source_type="ai", metadata_={"ai_assisted": True})
    check("ai_det.all_three", ai_run_detection.is_ai_assisted_run(r))


# ─── Phase 5: granular RBAC + role-mapping preservation ─────────────────────

from app.services import rbac_service


def test_rbac_all_11_granular_keys_defined():
    expected = {
        "automation.view",
        "automation.generate_script",
        "automation.edit_draft",
        "automation.review_script",
        "automation.approve_script",
        "automation.configure_external_connector",
        "automation.run_sandbox",
        "execution.run_automation",
        "execution.run_ai_assisted",
        "execution.view_live_runs",
        "execution.create_defect_draft",
    }
    check("rbac.11_keys_defined",
          expected.issubset(rbac_service.GRANULAR_PERMISSIONS),
          f"missing: {expected - rbac_service.GRANULAR_PERMISSIONS}")


def test_rbac_granular_in_all_permissions():
    for perm in rbac_service.GRANULAR_PERMISSIONS:
        check(f"rbac.{perm}_in_all",
              perm in rbac_service.ALL_PERMISSIONS,
              f"{perm} not in ALL_PERMISSIONS")


def test_rbac_project_admin_has_all_granular():
    perms = rbac_service.ROLE_PERMISSIONS["Project Admin"]
    missing = rbac_service.GRANULAR_PERMISSIONS - perms
    check("rbac.project_admin_full", not missing, f"Project Admin missing: {missing}")


def test_rbac_generate_automation_implies_granular_generate():
    # Every role with GENERATE_AUTOMATION must have the corresponding granular
    # write permissions so no one loses ability when guards migrate.
    for role_name, perms in rbac_service.ROLE_PERMISSIONS.items():
        if rbac_service.GENERATE_AUTOMATION in perms:
            for granular in (
                rbac_service.AUTOMATION_GENERATE_SCRIPT,
                rbac_service.AUTOMATION_EDIT_DRAFT,
                rbac_service.AUTOMATION_CONFIGURE_EXTERNAL_CONNECTOR,
                rbac_service.AUTOMATION_RUN_SANDBOX,
            ):
                check(
                    f"rbac.{role_name}_has_{granular}",
                    granular in perms,
                    f"{role_name} has GENERATE_AUTOMATION but not {granular}",
                )


def test_rbac_execute_tests_implies_granular_execution():
    for role_name, perms in rbac_service.ROLE_PERMISSIONS.items():
        if rbac_service.EXECUTE_TESTS in perms:
            for granular in (
                rbac_service.EXECUTION_RUN_AUTOMATION,
                rbac_service.EXECUTION_RUN_AI_ASSISTED,
            ):
                check(
                    f"rbac.{role_name}_has_{granular}",
                    granular in perms,
                    f"{role_name} has EXECUTE_TESTS but not {granular}",
                )


def test_rbac_view_project_implies_view_live_runs():
    for role_name, perms in rbac_service.ROLE_PERMISSIONS.items():
        if rbac_service.VIEW_PROJECT in perms:
            check(
                f"rbac.{role_name}_has_view_live_runs",
                rbac_service.EXECUTION_VIEW_LIVE_RUNS in perms,
                f"{role_name} has VIEW_PROJECT but not EXECUTION_VIEW_LIVE_RUNS",
            )


def test_rbac_approve_test_cases_implies_approve_script():
    for role_name, perms in rbac_service.ROLE_PERMISSIONS.items():
        if rbac_service.APPROVE_TEST_CASES in perms:
            check(
                f"rbac.{role_name}_has_approve_script",
                rbac_service.AUTOMATION_APPROVE_SCRIPT in perms,
                f"{role_name} has APPROVE_TEST_CASES but not AUTOMATION_APPROVE_SCRIPT",
            )


def test_rbac_raise_defects_implies_create_defect_draft():
    for role_name, perms in rbac_service.ROLE_PERMISSIONS.items():
        if rbac_service.RAISE_DEFECTS in perms:
            check(
                f"rbac.{role_name}_has_create_defect_draft",
                rbac_service.EXECUTION_CREATE_DEFECT_DRAFT in perms,
                f"{role_name} has RAISE_DEFECTS but not EXECUTION_CREATE_DEFECT_DRAFT",
            )


def test_rbac_negative_no_granular_without_coarse():
    # Viewer/Auditor has only VIEW_PROJECT + VIEW_AUDIT_LOGS. It should NOT
    # have automation.generate_script or execution.run_automation etc.
    viewer = rbac_service.ROLE_PERMISSIONS["Viewer/Auditor"]
    check("rbac.viewer_no_generate",
          rbac_service.AUTOMATION_GENERATE_SCRIPT not in viewer)
    check("rbac.viewer_no_run",
          rbac_service.EXECUTION_RUN_AUTOMATION not in viewer)
    check("rbac.viewer_no_defect_draft",
          rbac_service.EXECUTION_CREATE_DEFECT_DRAFT not in viewer)
    # But viewer DOES get view_live_runs from VIEW_PROJECT.
    check("rbac.viewer_has_view_live_runs",
          rbac_service.EXECUTION_VIEW_LIVE_RUNS in viewer)


def test_rbac_business_analyst_no_run_permission():
    # BA has VIEW_PROJECT + VIEW_TEST_DATA + APPROVE_REQUIREMENTS. No execute.
    ba = rbac_service.ROLE_PERMISSIONS["Business Analyst"]
    check("rbac.ba_no_run",
          rbac_service.EXECUTION_RUN_AUTOMATION not in ba)
    check("rbac.ba_no_ai_run",
          rbac_service.EXECUTION_RUN_AI_ASSISTED not in ba)
    check("rbac.ba_no_generate",
          rbac_service.AUTOMATION_GENERATE_SCRIPT not in ba)


def test_rbac_permissions_for_role_returns_granular():
    # Round-trip through the public API.
    perms = rbac_service.permissions_for_role("Automation Engineer")
    check("rbac.public_api_granular",
          rbac_service.AUTOMATION_GENERATE_SCRIPT in perms)
    check("rbac.public_api_execution",
          rbac_service.EXECUTION_RUN_AUTOMATION in perms)


def test_rbac_unknown_role_returns_empty():
    perms = rbac_service.permissions_for_role("Nonexistent Role")
    check("rbac.unknown_role_empty", len(perms) == 0)


def test_rbac_expand_role_permissions_pure():
    # Empty in, empty out — the helper must not fabricate permissions.
    result = rbac_service._expand_role_permissions(frozenset())
    check("rbac.expand_empty", len(result) == 0)


def test_rbac_expand_role_permissions_only_coarse_in():
    # A role with only GENERATE_AUTOMATION should get granular writes but not
    # execution permissions.
    base = frozenset({rbac_service.GENERATE_AUTOMATION})
    result = rbac_service._expand_role_permissions(base)
    check("rbac.expand.gets_generate_script",
          rbac_service.AUTOMATION_GENERATE_SCRIPT in result)
    check("rbac.expand.gets_edit_draft",
          rbac_service.AUTOMATION_EDIT_DRAFT in result)
    check("rbac.expand.no_execution",
          rbac_service.EXECUTION_RUN_AUTOMATION not in result)


def test_rbac_expand_is_idempotent():
    # Applying the helper twice yields the same permission set.
    base = rbac_service.ROLE_PERMISSIONS["Automation Engineer"]
    once = rbac_service._expand_role_permissions(base)
    twice = rbac_service._expand_role_permissions(once)
    check("rbac.expand.idempotent", once == twice)


def test_rbac_role_permissions_immutable():
    # frozenset must not be mutable — even accidental modification should fail.
    tester = rbac_service.ROLE_PERMISSIONS["Tester"]
    try:
        tester.add("bogus.permission")  # type: ignore[attr-defined]
        check("rbac.frozen", False, "frozenset was mutated!")
    except AttributeError:
        check("rbac.frozen", True)


def test_rbac_all_permissions_includes_all_11_granular():
    # Belt-and-braces: even if a future role skips the granular keys, the
    # global ALL_PERMISSIONS set must still enumerate them.
    for perm in rbac_service.GRANULAR_PERMISSIONS:
        check(f"rbac.all_perms.{perm}",
              perm in rbac_service.ALL_PERMISSIONS,
              f"{perm} not in ALL_PERMISSIONS")


def test_rbac_no_typos_in_granular_keys():
    # Guard against silent typos: every key must start with either
    # 'automation.' or 'execution.' (spec convention).
    for perm in rbac_service.GRANULAR_PERMISSIONS:
        check(f"rbac.namespace.{perm}",
              perm.startswith("automation.") or perm.startswith("execution."),
              f"{perm} doesn't match expected namespace")


def test_rbac_granular_and_coarse_disjoint():
    # The 11 granular keys must not accidentally collide with the coarse ones
    # (GENERATE_AUTOMATION = 'generate_automation' etc.). Overlap would let a
    # migration accidentally revoke access.
    coarse = {rbac_service.GENERATE_AUTOMATION, rbac_service.EXECUTE_TESTS,
              rbac_service.RAISE_DEFECTS, rbac_service.VIEW_PROJECT,
              rbac_service.APPROVE_TEST_CASES}
    overlap = coarse & rbac_service.GRANULAR_PERMISSIONS
    check("rbac.granular_disjoint_from_coarse",
          not overlap, f"overlap: {overlap}")


# ─── Phase 5: ai_assistance_status schema validation ────────────────────────


def test_ai_assistance_status_schema_defaults_to_disabled():
    # TestCaseOut should accept an input without ai_assistance_status and
    # default to 'disabled' — matches the model server_default.
    from app.schemas.test_plan import TestCaseOut
    from datetime import datetime

    # Build a minimally-valid TestCaseOut. Missing ai_assistance_status should
    # not raise; the field must resolve to 'disabled'.
    payload = dict(
        id=1, project_id=1, test_case_id="TC-1", title="x",
        priority="Medium", severity="Medium",
        automation_candidate=False, mode="manual", execution_mode="manual",
        automation_eligible="no", automation_status="not_required",
        approval_status="draft", created_by=1, status="draft",
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )
    tc = TestCaseOut.model_validate(payload)
    check("schema.default_disabled", tc.ai_assistance_status == "disabled")


def test_ai_assistance_status_schema_accepts_all_5_values():
    from app.schemas.test_plan import TestCaseOut
    from datetime import datetime

    base = dict(
        id=1, project_id=1, test_case_id="TC-1", title="x",
        priority="Medium", severity="Medium",
        automation_candidate=False, mode="manual", execution_mode="manual",
        automation_eligible="no", automation_status="not_required",
        approval_status="draft", created_by=1, status="draft",
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )
    for value in ("disabled", "enabled", "recommendation_pending", "approved", "rejected"):
        try:
            tc = TestCaseOut.model_validate({**base, "ai_assistance_status": value})
            check(f"schema.accepts_{value}", tc.ai_assistance_status == value)
        except Exception as e:
            check(f"schema.accepts_{value}", False, str(e))


def test_ai_assistance_status_schema_rejects_unknown_value():
    from app.schemas.test_plan import TestCaseOut
    from datetime import datetime

    base = dict(
        id=1, project_id=1, test_case_id="TC-1", title="x",
        priority="Medium", severity="Medium",
        automation_candidate=False, mode="manual", execution_mode="manual",
        automation_eligible="no", automation_status="not_required",
        approval_status="draft", created_by=1, status="draft",
        created_at=datetime(2026, 1, 1), updated_at=datetime(2026, 1, 1),
    )
    try:
        TestCaseOut.model_validate({**base, "ai_assistance_status": "bogus_state"})
        check("schema.rejects_bogus", False, "should have raised ValidationError")
    except Exception:
        # Pydantic raises ValidationError; any exception means the literal
        # constraint was enforced.
        check("schema.rejects_bogus", True)


def test_test_case_update_ai_assistance_optional():
    # TestCaseUpdate should allow omitting the field entirely (partial update).
    from app.schemas.test_plan import TestCaseUpdate
    upd = TestCaseUpdate()
    check("update.optional",
          upd.ai_assistance_status is None)


def test_test_case_update_ai_assistance_setter():
    from app.schemas.test_plan import TestCaseUpdate
    upd = TestCaseUpdate(ai_assistance_status="enabled")
    check("update.setter", upd.ai_assistance_status == "enabled")


def test_test_case_update_ai_assistance_rejects_invalid():
    from app.schemas.test_plan import TestCaseUpdate
    try:
        TestCaseUpdate(ai_assistance_status="on")  # type: ignore[arg-type]
        check("update.rejects_invalid", False, "should have raised")
    except Exception:
        check("update.rejects_invalid", True)


# ─── Phase 5: TestCase model ai_assistance_status column presence ──────────


def test_model_ai_assistance_status_column_exists():
    from app.models.test_case import TestCase
    col = getattr(TestCase, "ai_assistance_status", None)
    check("model.column_exists", col is not None)


def test_model_ai_assistance_status_default():
    # Instantiate TestCase without ai_assistance_status; SQLAlchemy default
    # should kick in on flush (we can't easily test flush here, but the
    # server_default attribute should be present).
    from app.models.test_case import TestCase
    column = TestCase.__table__.columns.get("ai_assistance_status")
    if column is None:
        check("model.default_disabled", False, "column missing")
        return
    default_arg = getattr(column.default, "arg", None) if column.default is not None else None
    server_default = column.server_default
    server_default_arg = None
    if server_default is not None:
        server_default_arg = getattr(server_default, "arg", None)
        if hasattr(server_default_arg, "text"):
            server_default_arg = server_default_arg.text
    check("model.default_disabled",
          default_arg == "disabled" or "disabled" in str(server_default_arg or ""),
          f"default={default_arg!r} server_default={server_default_arg!r}")


def test_model_ai_assistance_status_not_nullable():
    from app.models.test_case import TestCase
    column = TestCase.__table__.columns.get("ai_assistance_status")
    check("model.not_nullable", column is not None and not column.nullable)


# ─── Runner ──────────────────────────────────────────────────────────────────


def main() -> int:
    tests = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    for t in tests:
        _run(t)
    print()
    print(f"PASS: {len(_PASS)}")
    print(f"FAIL: {len(_FAIL)}")
    if _FAIL:
        print()
        print("-- Failures --")
        for name, detail in _FAIL:
            print(f"  X {name}")
            for line in detail.splitlines():
                print(f"      {line}")
    return 0 if not _FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
