"""UI-019 recording -> Automation IR.

The emitter's whole job is to be honest about what was observed. These tests
pin the three ways it is allowed to fall short — a `custom` step, an
unrenderable checkpoint, an unbound literal — and prove that in every case the
shortfall lands in `readiness` rather than being papered over with a guess.

The emitted contract is validated by `AutomationGenerationContract` itself, so
a test that constructs one at all is already asserting that every step and
assertion target resolves to a declared page-object element.
"""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.services.recorder import ir_emitter
from app.services.recorder.context import RecordingContext

NOW = datetime(2026, 7, 27, 12, 0, tzinfo=timezone.utc)


def _context(**overrides):
    base = dict(
        session=SimpleNamespace(
            id=1,
            project_id=1,
            environment="QA",
            framework="playwright",
            requirement_ref="REQ-1",
            status="STOPPED",
        ),
        test_case=SimpleNamespace(
            id=8, test_case_id="TC-0008", title="Place an order", test_type="e2e", preconditions=["Logged in"],
            steps=[{"step_number": 1, "action": "Search", "expected_result": "Results shown"}],
        ),
        suite=None,
        member=None,
        application=None,
        application_model=None,
        actions=[],
        mappings=[],
        step_states=[],
        checkpoints=[],
        segments=[],
        bindings=[],
        notes=[],
        captures=[],
        events=[],
    )
    base.update(overrides)
    return RecordingContext(**base)


def _locator_evidence(name="search_box", strategy="role", value="Search", role="combobox"):
    return {
        "element_name": name,
        "role": role,
        "page_url": "https://shop.example.com/customer/search",
        "candidates": [
            {"strategy": strategy, "value": value, "locator": f"getByRole('{role}')", "confidence": 90,
             "unique": True, "validated": True},
        ],
    }


def _action(sequence, family, *, action_id=None, locator=None, binding=None, inclusion="included"):
    return SimpleNamespace(
        id=action_id if action_id is not None else sequence + 1,
        sequence=sequence,
        action_family=family,
        inclusion_state=inclusion,
        target_semantic=f"{family} target",
        input_binding=binding,
        locator_evidence=locator,
        locator_confidence=90 if locator else None,
        occurred_at=NOW,
    )


def _mapping(action_id, step_key="1", **kwargs):
    return SimpleNamespace(
        action_id=action_id,
        step_key=step_key,
        excluded_from_ir=kwargs.get("excluded_from_ir", False),
        lifecycle_phase=kwargs.get("lifecycle_phase"),
        mapping_source="active_step",
    )


def _checkpoint(checkpoint_type, *, review_state="accepted", action_id=None, expected="x", source="user", cp_id=1):
    return SimpleNamespace(
        id=cp_id,
        checkpoint_type=checkpoint_type,
        review_state=review_state,
        action_id=action_id,
        step_key="1",
        expected_value=expected,
        source=source,
        target=expected,
    )


def _binding(name="search_query", classification="static_value", **kwargs):
    return SimpleNamespace(
        name=name,
        placeholder=f"${{{name}}}",
        classification=classification,
        sample_value=kwargs.get("sample_value", "widget"),
        secret_reference=kwargs.get("secret_reference"),
        action_id=kwargs.get("action_id"),
    )


def _kinds(result):
    return {item["kind"] for item in result.readiness["unresolved"]}


# ── Happy path ───────────────────────────────────────────────────────────────


def test_navigate_and_click_become_contract_steps():
    context = _context(
        actions=[
            _action(0, "navigate", action_id=1, binding={"url": "https://shop.example.com/"}),
            _action(1, "click", action_id=2, locator=_locator_evidence()),
        ],
        mappings=[_mapping(1), _mapping(2)],
    )
    result = ir_emitter.build(context)

    assert [s.action for s in result.contract.steps] == ["navigate", "click"]
    assert result.contract.steps[0].value == "https://shop.example.com/"
    # navigate targets a raw path, never a page-object element.
    assert result.contract.steps[0].target is None
    assert result.contract.steps[1].target == "CustomerSearchPage.search_box"
    assert result.source_action_ids == [1, 2]
    assert result.readiness["unresolved_count"] == 0


def test_page_objects_are_grouped_by_page_and_deduped_by_locator():
    evidence = _locator_evidence()
    context = _context(
        actions=[
            _action(0, "click", action_id=1, locator=evidence),
            _action(1, "click", action_id=2, locator=evidence),
        ],
        mappings=[_mapping(1), _mapping(2)],
    )
    result = ir_emitter.build(context)
    assert len(result.contract.page_objects) == 1
    assert len(result.contract.page_objects[0].elements) == 1


def test_distinct_elements_on_one_page_get_unique_names():
    context = _context(
        actions=[
            _action(0, "click", action_id=1, locator=_locator_evidence(value="Search")),
            _action(1, "click", action_id=2, locator=_locator_evidence(value="Reset")),
        ],
        mappings=[_mapping(1), _mapping(2)],
    )
    result = ir_emitter.build(context)
    names = [element.name for element in result.contract.page_objects[0].elements]
    assert names == ["search_box", "search_box_2"]


# ── Honest shortfalls ────────────────────────────────────────────────────────


def test_action_without_a_locator_becomes_a_custom_step_not_a_guess():
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=None)],
        mappings=[_mapping(1)],
    )
    result = ir_emitter.build(context)
    step = result.contract.steps[0]
    assert step.action == "custom"
    assert step.target is None
    assert step.description
    assert "no_locator" in _kinds(result)
    assert result.readiness["custom_step_count"] == 1


def test_unmapped_action_is_excluded_and_reported():
    context = _context(actions=[_action(0, "click", action_id=1, locator=_locator_evidence())])
    result = ir_emitter.build(context)
    assert result.contract.steps == []
    assert "unmapped_action" in _kinds(result)


def test_explicitly_excluded_action_is_dropped_silently():
    """It was a deliberate decision, so it is not reported as a shortfall."""
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=_locator_evidence())],
        mappings=[_mapping(1, excluded_from_ir=True)],
    )
    result = ir_emitter.build(context)
    assert result.contract.steps == []
    assert _kinds(result) == set()


def test_observations_are_not_steps_and_not_gaps():
    context = _context(actions=[_action(0, "read", action_id=1)], mappings=[_mapping(1)])
    result = ir_emitter.build(context)
    assert result.contract.steps == []
    assert _kinds(result) == set()


def test_unbound_typed_value_is_hard_coded_and_reported():
    context = _context(
        actions=[_action(0, "input", action_id=1, locator=_locator_evidence(), binding={"text": "widget"})],
        mappings=[_mapping(1)],
    )
    result = ir_emitter.build(context)
    assert result.contract.steps[0].value == "widget"
    assert "unbound_input" in _kinds(result)


def test_bound_input_uses_the_data_binding_instead_of_a_literal():
    context = _context(
        actions=[_action(0, "input", action_id=1, locator=_locator_evidence(), binding={"text": "widget"})],
        mappings=[_mapping(1)],
        bindings=[_binding(action_id=1)],
    )
    result = ir_emitter.build(context)
    step = result.contract.steps[0]
    assert step.data_binding == "search_query"
    assert step.value is None
    assert "unbound_input" not in _kinds(result)


# ── Checkpoints (Section 16) ─────────────────────────────────────────────────


def test_only_accepted_checkpoints_become_assertions():
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=_locator_evidence())],
        mappings=[_mapping(1)],
        checkpoints=[
            _checkpoint("element_visible", action_id=1, review_state="accepted", cp_id=1),
            _checkpoint("element_visible", action_id=1, review_state="needs_review", source="recommended", cp_id=2),
        ],
    )
    result = ir_emitter.build(context)
    assert len(result.contract.assertions) == 1
    assert "unreviewed_recommendation" in _kinds(result)


def test_url_checkpoint_targets_the_page():
    context = _context(
        actions=[_action(0, "navigate", action_id=1, binding={"url": "https://shop.example.com/"})],
        mappings=[_mapping(1)],
        checkpoints=[_checkpoint("url_matches", expected="https://shop.example.com/")],
    )
    result = ir_emitter.build(context)
    assertion = result.contract.assertions[0]
    assert assertion.type == "url"
    assert assertion.target == "page"


@pytest.mark.parametrize("checkpoint_type", ["element_hidden", "title_matches", "no_severe_console_errors", "api_status"])
def test_checkpoint_types_the_contract_cannot_express_are_reported_not_approximated(checkpoint_type):
    """Rendering element_hidden as a `visible` assertion would invert it."""
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=_locator_evidence())],
        mappings=[_mapping(1)],
        checkpoints=[_checkpoint(checkpoint_type, action_id=1)],
    )
    result = ir_emitter.build(context)
    assert result.contract.assertions == []
    assert "unrenderable_checkpoint" in _kinds(result)


def test_element_checkpoint_without_a_resolvable_element_is_reported():
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=None)],
        mappings=[_mapping(1)],
        checkpoints=[_checkpoint("element_visible", action_id=1)],
    )
    result = ir_emitter.build(context)
    assert result.contract.assertions == []
    assert "checkpoint_without_element" in _kinds(result)


# ── Security: secrets (Section 18) ───────────────────────────────────────────


def test_secret_reference_never_carries_a_value_into_the_ir():
    context = _context(bindings=[_binding("password", "secret_reference", sample_value=None, secret_reference="vault://pw")])
    result = ir_emitter.build(context)
    binding = result.contract.test_data_bindings[0]
    assert binding.name == "password"
    assert binding.fallback is None
    assert "secret_reference" in _kinds(result)


def test_a_secret_binding_carrying_a_stray_value_still_emits_no_value():
    """Defence in depth: the DB constraint forbids this, and so does the emitter."""
    context = _context(bindings=[_binding("password", "secret_reference", sample_value="hunter2")])
    result = ir_emitter.build(context)
    assert result.contract.test_data_bindings[0].fallback is None


# ── Environment and framework mapping ────────────────────────────────────────


@pytest.mark.parametrize("environment,expected", [("QA", "QA"), ("sit", "SIT"), ("Prod Sanity", "PROD_SANITY")])
def test_known_environments_map_to_contract_profiles(environment, expected):
    context = _context(session=SimpleNamespace(
        id=1, project_id=1, environment=environment, framework="playwright",
        requirement_ref=None, status="STOPPED",
    ))
    result = ir_emitter.build(context)
    assert result.contract.environment_profile == expected
    assert "environment_profile" not in _kinds(result)


def test_unknown_environment_is_recorded_as_qa_and_flagged():
    context = _context(session=SimpleNamespace(
        id=1, project_id=1, environment="staging-3", framework="playwright",
        requirement_ref=None, status="STOPPED",
    ))
    result = ir_emitter.build(context)
    assert result.contract.environment_profile == "QA"
    assert "environment_profile" in _kinds(result)


def test_unknown_framework_is_flagged_rather_than_silently_defaulted():
    context = _context(session=SimpleNamespace(
        id=1, project_id=1, environment="QA", framework="katalon",
        requirement_ref=None, status="STOPPED",
    ))
    result = ir_emitter.build(context)
    assert result.contract.script_type == "playwright-typescript"
    assert "script_type" in _kinds(result)


# ── Lifecycle phases ─────────────────────────────────────────────────────────


def test_setup_actions_land_in_the_arrange_phase():
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=_locator_evidence())],
        mappings=[_mapping(1, lifecycle_phase="setup")],
    )
    assert ir_emitter.build(context).contract.steps[0].phase == "arrange"


def test_teardown_actions_become_cleanup_actions_not_steps():
    context = _context(
        actions=[_action(0, "click", action_id=1, locator=_locator_evidence())],
        mappings=[_mapping(1, lifecycle_phase="teardown")],
    )
    result = ir_emitter.build(context)
    assert result.contract.steps == []
    assert len(result.contract.cleanup_actions) == 1
    assert result.contract.cleanup_actions[0].target == "CustomerSearchPage.search_box"


# ── Traceability (Section 22) ────────────────────────────────────────────────


def test_contract_carries_test_case_requirement_and_preconditions():
    result = ir_emitter.build(_context())
    assert result.contract.test_case_id == "TC-0008"
    assert result.contract.requirement_id == "REQ-1"
    assert result.contract.preconditions == ["Logged in"]
    assert result.contract.expected_results == ["Results shown"]


def test_readiness_is_only_clean_when_something_was_emitted():
    empty = ir_emitter.build(_context())
    assert empty.readiness["ready_for_script_generation"] is False

    context = _context(
        actions=[_action(0, "navigate", action_id=1, binding={"url": "https://shop.example.com/"})],
        mappings=[_mapping(1)],
    )
    assert ir_emitter.build(context).readiness["ready_for_script_generation"] is True
