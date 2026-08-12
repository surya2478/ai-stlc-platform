"""Focused tests for the studio's grounding, discovery and dry-run layer.

DB-free, matching test_test_automation_studio.py: everything asserted here is
a pure decision — how a step is matched against a discovered element, what a
credential blob round-trips to, which frameworks can execute, and what shape
the compiled bundle hands the runner. The live crawl and the real browser
execution are covered by the walkthrough, not simulated here.

Usage:
    python -m pytest tests/test_tas_grounding.py -q
    python tests/test_tas_grounding.py
"""
from __future__ import annotations

import os
import sys
import traceback

_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_ROOT = os.path.dirname(_HERE)
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

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


from app.agents.test_automation_studio.discovery_agent import (
    _find_control,
    _hosts_for,
    _looks_like_password_field,
)
from app.agents.automation.snapshot_parser import parse_snapshot
from app.models.test_automation_studio import TasRefinedTestCase, TasScriptAsset
from app.services.test_automation_studio import (
    discovery_service,
    dry_run_service,
    grounding_service,
    intake_service,
)
from app.services.test_automation_studio.script_lab_service import _gate_subject, _test_case_payload


def _catalog() -> list[dict]:
    return [
        {
            "element_name": "textbox_username",
            "page": "https://app.test/login",
            "role": "textbox",
            "accessible_name": "Username",
            "business_meaning": "identifies the signing-in user",
            "recommended_locator": "page.getByRole('textbox', { name: 'Username', exact: true })",
            "recommended_strategy": "role",
            "confidence_score": 90,
        },
        {
            "element_name": "textbox_password",
            "page": "https://app.test/login",
            "role": "textbox",
            "accessible_name": "Password",
            "business_meaning": "the account password",
            "recommended_locator": "page.getByRole('textbox', { name: 'Password', exact: true })",
            "recommended_strategy": "role",
            "confidence_score": 90,
        },
        {
            "element_name": "button_continue",
            "page": "https://app.test/login",
            "role": "button",
            "accessible_name": "Continue",
            "business_meaning": "submits the login form",
            "recommended_locator": "page.getByRole('button', { name: 'Continue', exact: true })",
            "recommended_strategy": "role",
            "confidence_score": 90,
        },
    ]


def _test_case(steps: list[dict]) -> TasRefinedTestCase:
    return TasRefinedTestCase(
        project_id=1,
        origin="derived",
        tc_display_id="TC-0001",
        title="Sign in with valid credentials",
        steps=steps,
        priority="High",
        classification="automation",
        status="approved",
        created_by=1,
    )


# ── Step → element matching ──────────────────────────────────────────────────

def test_step_matches_on_accessible_name():
    result = grounding_service.ground_test_case(
        _test_case([{"step_number": 1, "action": "Enter the username", "target": "Username field"}]),
        _catalog(),
    )
    matched = result["summary"]["matched"]
    check("grounding.exact_name_match", result["status"] == "grounded", str(result["status"]))
    check(
        "grounding.binds_the_right_element",
        len(matched) == 1 and matched[0]["element_name"] == "textbox_username",
        str(matched),
    )


def test_role_affinity_beats_word_overlap():
    """A step that types cannot be satisfied by a button.

    "Enter the password" overlaps "submits the login form" through shared
    words, and without role affinity a high text score could bind a fill step
    to the submit button — which then hangs at runtime rather than failing
    with anything readable.
    """
    result = grounding_service.ground_test_case(
        _test_case([{"step_number": 1, "action": "Type the password", "target": "Password"}]),
        _catalog(),
    )
    matched = result["summary"]["matched"]
    check(
        "grounding.role_affinity_holds",
        len(matched) == 1 and matched[0]["element_name"] == "textbox_password",
        str(matched),
    )


def test_label_mismatch_is_reported_not_guessed():
    """The whole point of grounding: a control the document names differently
    from the application must surface as a gap, not a confident wrong match."""
    result = grounding_service.ground_test_case(
        _test_case(
            [{"step_number": 1, "action": "Click the Frobnicate widget", "target": "Frobnicate widget"}]
        ),
        _catalog(),
    )
    unresolved = result["summary"]["unresolved"]
    check("grounding.unmatched_is_ungrounded", result["status"] == "ungrounded", str(result["status"]))
    check(
        "grounding.gap_names_the_target",
        len(unresolved) == 1 and "Frobnicate widget" in (unresolved[0]["reason"] or ""),
        str(unresolved),
    )


def test_partial_grounding_reports_both_sides():
    result = grounding_service.ground_test_case(
        _test_case(
            [
                {"step_number": 1, "action": "Enter the username", "target": "Username"},
                {"step_number": 2, "action": "Click the Teleport button", "target": "Teleport button"},
            ]
        ),
        _catalog(),
    )
    summary = result["summary"]
    check(
        "grounding.partial_status",
        result["status"] == "partially_grounded",
        str(result["status"]),
    )
    check(
        "grounding.partial_counts",
        summary["matched_steps"] == 1 and len(summary["unresolved"]) == 1,
        str(summary),
    )


def test_navigation_steps_are_skipped_not_failed():
    """A step with no control to touch is not a grounding failure. Counting it
    as one would bury the gaps that matter under noise."""
    result = grounding_service.ground_test_case(
        _test_case(
            [
                {"step_number": 1, "action": "Navigate to the login page", "target": "login page"},
                {"step_number": 2, "action": "Enter the username", "target": "Username"},
            ]
        ),
        _catalog(),
    )
    summary = result["summary"]
    check("grounding.navigation_skipped", summary["skipped_steps"] == 1, str(summary))
    check("grounding.remaining_grounded", result["status"] == "grounded", str(result["status"]))


def test_ambiguous_match_refuses_rather_than_picks():
    """Two equally good candidates must produce a gap the user can fix, not a
    coin flip that silently binds the wrong one."""
    catalog = [
        {
            "element_name": "button_delete_1",
            "role": "button",
            "accessible_name": "Delete",
            "recommended_locator": "page.getByRole('button', { name: 'Delete', exact: true })",
            "confidence_score": 90,
        },
        {
            "element_name": "button_delete_2",
            "role": "button",
            "accessible_name": "Delete",
            "recommended_locator": "page.getByRole('button', { name: 'Delete', exact: true }).nth(1)",
            "confidence_score": 90,
        },
    ]
    entry, reason = grounding_service.match_step(
        {"action": "Click Delete row action", "target": "Delete row action"}, catalog
    )
    check("grounding.ambiguous_refuses", entry is None, str(entry))
    check(
        "grounding.ambiguous_explains",
        reason is not None and "more than one" in reason,
        str(reason),
    )


def test_no_ui_steps_is_ungrounded_with_a_note():
    result = grounding_service.ground_test_case(
        _test_case([{"step_number": 1, "action": "Wait for the batch job", "target": None}]),
        _catalog(),
    )
    check("grounding.no_targets_ungrounded", result["status"] == "ungrounded", str(result["status"]))
    check(
        "grounding.no_targets_explained",
        bool(result["summary"]["note"]),
        "an ungrounded verdict with no groundable steps must explain itself",
    )


# ── Credentials ──────────────────────────────────────────────────────────────

def test_credentials_round_trip():
    blob = discovery_service.encrypt_credentials({"username": "svc_qa", "password": "hunter2"})
    check("credentials.encrypted", blob is not None and "hunter2" not in blob, str(blob))
    check(
        "credentials.round_trip",
        discovery_service.decrypt_credentials(blob) == {"username": "svc_qa", "password": "hunter2"},
    )


def test_partial_credentials_are_not_stored():
    check(
        "credentials.username_only_rejected",
        discovery_service.encrypt_credentials({"username": "svc_qa"}) is None,
    )
    check("credentials.empty_rejected", discovery_service.encrypt_credentials({}) is None)


def test_undecryptable_blob_degrades_quietly():
    """A rotated app secret must leave discovery signing in as nobody, not
    crash the worker mid-run."""
    check(
        "credentials.garbage_is_empty",
        discovery_service.decrypt_credentials("not-a-fernet-token") == {},
    )
    check("credentials.none_is_empty", discovery_service.decrypt_credentials(None) == {})


def test_auth_mode_none_clears_the_secret():
    from app.models.test_automation_studio import TasIntakeBatch

    batch = TasIntakeBatch(
        project_id=1, name="b", application_environment="qa", auth_mode="form", created_by=1
    )
    batch.auth_secret_encrypted = discovery_service.encrypt_credentials(
        {"username": "u", "password": "p"}
    )
    discovery_service.apply_auth_settings(batch, {"auth_mode": "none"}, user_id=1)
    check(
        "credentials.disabling_clears",
        batch.auth_secret_encrypted is None,
        "turning sign-in off must remove the password, not merely stop using it",
    )


def test_relabelling_keeps_stored_credentials():
    from app.models.test_automation_studio import TasIntakeBatch

    batch = TasIntakeBatch(
        project_id=1, name="b", application_environment="qa", auth_mode="form", created_by=1
    )
    stored = discovery_service.encrypt_credentials({"username": "u", "password": "p"})
    batch.auth_secret_encrypted = stored
    discovery_service.apply_auth_settings(
        batch,
        {"auth_mode": "form", "auth_config": {"username_label": "Email"}},
        user_id=1,
    )
    check(
        "credentials.relabel_preserves",
        batch.auth_secret_encrypted == stored,
        "editing a field label must not wipe the password",
    )
    check(
        "credentials.config_filtered",
        batch.auth_config == {"username_label": "Email"},
        str(batch.auth_config),
    )


# ── Login form detection ─────────────────────────────────────────────────────

_LOGIN_SNAPSHOT = """### Page
- Page URL: https://app.test/login
- Page Title: Sign in
### Snapshot
```yaml
- generic [ref=e1]:
  - textbox "Email address" [ref=e2]
  - textbox "Password" [ref=e3]
  - button "Continue" [ref=e4]
```
"""


def test_login_fields_found_by_label():
    parsed = parse_snapshot(_LOGIN_SNAPSHOT)
    username = _find_control(parsed, roles=("textbox",), label="Email", hints=())
    password = _find_control(parsed, roles=("textbox",), label=None, hints=("password",))
    check("login.username_by_label", username is not None and username.ref == "e2", str(username))
    check("login.password_by_hint", password is not None and password.ref == "e3", str(password))


def test_wrong_label_refuses_rather_than_falls_back():
    """A supplied label that matches nothing must fail. Falling back to "the
    first textbox" is how a password gets typed into a search box."""
    parsed = parse_snapshot(_LOGIN_SNAPSHOT)
    found = _find_control(parsed, roles=("textbox",), label="Customer reference", hints=())
    check("login.wrong_label_refuses", found is None, str(found))


def test_password_field_still_present_means_sign_in_failed():
    parsed = parse_snapshot(_LOGIN_SNAPSHOT)
    check("login.failure_detected", _looks_like_password_field(parsed) is True)


def test_hosts_include_login_and_application():
    hosts = _hosts_for("https://app.test/home", "https://auth.test/login")
    check("login.both_hosts_allowed", hosts == ["app.test", "auth.test"], str(hosts))
    check("login.blank_ignored", _hosts_for(None, "") == [], str(_hosts_for(None, "")))


# ── Generation payload and gate ──────────────────────────────────────────────

def test_resolved_elements_reach_the_generator():
    """Grounding already worked out which element each step means; the
    generator is told, rather than made to repeat the matching."""
    test_case = _test_case([{"step_number": 1, "action": "Enter the username", "target": "Username"}])
    test_case.grounding_summary = {
        "matched": [
            {
                "step_number": 1,
                "target": "Username",
                "element_name": "textbox_username",
                "locator": "page.getByRole('textbox', { name: 'Username', exact: true })",
            }
        ]
    }
    payload = _test_case_payload(test_case)
    check(
        "generation.resolved_elements_passed",
        payload.get("resolved_elements", [{}])[0].get("element_name") == "textbox_username",
        str(payload.get("resolved_elements")),
    )


def test_ungrounded_test_case_payload_has_no_resolved_key():
    payload = _test_case_payload(_test_case([{"step_number": 1, "action": "Click", "target": "X"}]))
    check("generation.no_phantom_key", "resolved_elements" not in payload, str(payload.keys()))


def test_gate_sees_the_whole_bundle():
    """Locators live in page objects, not the spec. A gate handed only the
    entry file would pass a bundle whose every locator was an xpath."""
    subject = _gate_subject(
        None,
        "playwright",
        "import { test } from '@playwright/test';",
        {"pages/LoginPage.ts": "export const x = 1;"},
        "specs/tc-0001.spec.ts",
    )
    check(
        "gate.bundle_includes_entry",
        "specs/tc-0001.spec.ts" in subject.compiled_files,
        str(sorted(subject.compiled_files)),
    )
    check(
        "gate.bundle_includes_pages",
        "pages/LoginPage.ts" in subject.compiled_files,
        str(sorted(subject.compiled_files)),
    )
    check("gate.entry_path_is_file_path", subject.file_path == "specs/tc-0001.spec.ts")


# ── Dry run ──────────────────────────────────────────────────────────────────

def _script(**overrides) -> TasScriptAsset:
    defaults = dict(
        project_id=1,
        refined_test_case_id=1,
        framework="playwright",
        language="typescript",
        script_key="TC-0001.spec.ts",
        code="import { test } from '@playwright/test';",
        files={"pages/LoginPage.ts": "export const x = 1;"},
        entry_path="specs/tc-0001.spec.ts",
        created_by=1,
    )
    defaults.update(overrides)
    return TasScriptAsset(**defaults)


def test_compiled_bundle_materialises_whole_tree():
    """The spec imports its page objects by relative path. Handing the runner
    only the entry file produces an import that resolves to nothing."""
    payload = dry_run_service._script_payload(_script(), _test_case([]))
    files = payload["compiled_files"]
    check(
        "dry_run.bundle_complete",
        files is not None
        and "specs/tc-0001.spec.ts" in files
        and "pages/LoginPage.ts" in files,
        str(sorted(files or {})),
    )
    check("dry_run.entry_is_bundle_path", payload["file_path"] == "specs/tc-0001.spec.ts")


def test_freeform_script_runs_as_a_single_file():
    payload = dry_run_service._script_payload(
        _script(entry_path=None, files={}), _test_case([])
    )
    check("dry_run.freeform_no_bundle", payload["compiled_files"] is None, str(payload))
    check("dry_run.freeform_uses_script_key", payload["file_path"] == "TC-0001.spec.ts")


def test_only_playwright_is_runnable_here():
    check(
        "dry_run.playwright_runnable",
        "playwright" in dry_run_service.RUNNABLE_FRAMEWORKS,
    )
    for framework in ("katalon", "appium"):
        check(
            f"dry_run.{framework}_not_runnable",
            framework not in dry_run_service.RUNNABLE_FRAMEWORKS,
        )
        check(
            f"dry_run.{framework}_explains_why",
            bool(dry_run_service.BLOCKED_REASONS.get(framework)),
            "a blocked framework must say why, or the badge is unexplainable",
        )


# ── PATCH semantics: omitted vs. explicitly null ─────────────────────────────

def _batch():
    from app.models.test_automation_studio import TasIntakeBatch

    batch = TasIntakeBatch(
        project_id=1,
        name="Batch A",
        description="original",
        application_environment="qa",
        created_by=1,
    )
    batch.application_url = "https://app.test"
    batch.application_id = 7
    return batch


def test_omitted_field_is_left_alone():
    from app.schemas.test_automation_studio import IntakeBatchUpdate

    batch = _batch()
    intake_service.apply_batch_fields(batch, IntakeBatchUpdate(name="Batch B"))
    check("patch.name_applied", batch.name == "Batch B", batch.name)
    check("patch.url_untouched", batch.application_url == "https://app.test", str(batch.application_url))
    check("patch.app_untouched", batch.application_id == 7, str(batch.application_id))
    check("patch.description_untouched", batch.description == "original", str(batch.description))


def test_explicit_null_clears_the_url():
    """The whole point: blanking the field and saving has to stick.

    Before this, a null meant "leave alone", so the field appeared to save and
    the old value returned on the next read.
    """
    from app.schemas.test_automation_studio import IntakeBatchUpdate

    batch = _batch()
    intake_service.apply_batch_fields(batch, IntakeBatchUpdate(application_url=None))
    check("patch.url_cleared", batch.application_url is None, str(batch.application_url))
    check("patch.clearing_url_keeps_app", batch.application_id == 7, str(batch.application_id))


def test_explicit_null_unlinks_the_application():
    from app.schemas.test_automation_studio import IntakeBatchUpdate

    batch = _batch()
    intake_service.apply_batch_fields(batch, IntakeBatchUpdate(application_id=None))
    check("patch.app_unlinked", batch.application_id is None, str(batch.application_id))


def test_blank_string_url_is_normalised_to_a_clear():
    """The form sends "" when the user empties the box; the schema normalises
    that to null, which must then clear rather than store an empty string."""
    from app.schemas.test_automation_studio import IntakeBatchUpdate

    batch = _batch()
    intake_service.apply_batch_fields(batch, IntakeBatchUpdate(application_url="   "))
    check("patch.blank_url_cleared", batch.application_url is None, str(batch.application_url))


def test_not_null_columns_refuse_a_null():
    """`name` and `application_environment` have nothing to clear to, so a null
    is ignored instead of being allowed to fail at the database."""
    from app.schemas.test_automation_studio import IntakeBatchUpdate

    batch = _batch()
    intake_service.apply_batch_fields(
        batch, IntakeBatchUpdate(name=None, application_environment=None)
    )
    check("patch.name_kept", batch.name == "Batch A", str(batch.name))
    check("patch.environment_kept", batch.application_environment == "qa", str(batch.application_environment))


def test_name_is_trimmed():
    from app.schemas.test_automation_studio import IntakeBatchUpdate

    batch = _batch()
    intake_service.apply_batch_fields(batch, IntakeBatchUpdate(name="  Batch C  "))
    check("patch.name_trimmed", batch.name == "Batch C", repr(batch.name))


def test_assess_forwards_only_what_it_was_given():
    """An assess call naming a URL must not unlink the application by
    implication — `prepare_assessment` rebuilds the patch from the fields the
    request actually carried, not from every attribute on the model."""
    import inspect

    from app.services.test_automation_studio import coverage_service

    source = inspect.getsource(coverage_service.prepare_assessment)
    check(
        "patch.assess_uses_fields_set",
        "model_fields_set" in source,
        "prepare_assessment builds its patch from every attribute, which would "
        "turn each unmentioned setting into an explicit null",
    )


TESTS = [
    value
    for name, value in list(globals().items())
    if name.startswith("test_")
    and callable(value)
    and getattr(value, "__module__", None) == __name__
    and name != "test_all"
]


def test_all():
    """Single pytest entry point so the harness reports one result per file."""
    for fn in TESTS:
        _run(fn)
    assert not _FAIL, "\n".join(f"{name}: {detail}" for name, detail in _FAIL)


if __name__ == "__main__":
    for fn in TESTS:
        _run(fn)
    print(f"{len(_PASS)} passed, {len(_FAIL)} failed")
    for name, detail in _FAIL:
        print(f"  FAIL {name}: {detail}")
    sys.exit(1 if _FAIL else 0)
