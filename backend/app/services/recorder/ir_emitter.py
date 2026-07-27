"""Recording → Automation IR (Contract Section 22).

The IR is not a new format. It is `AutomationGenerationContract` — the same
validated, framework-neutral structure the script compiler already renders to
Playwright TypeScript and pytest. Recording simply became a second way to
produce one, alongside generation, which is why a recorded test case can reach
runnable code without anything here knowing what Playwright is.

The emitter is deterministic and pure over a loaded `RecordingContext`. It
never infers an action, a locator or an assertion:

- An action with no observed locator becomes a `custom` step, which the
  compiler renders as a visible TODO comment. It does not become a guessed
  selector.
- Only checkpoints a person accepted become assertions.
- A checkpoint type the contract cannot express is reported in `readiness`,
  not dropped and not approximated by a different assertion.

Everything the emitter could not resolve ends up in `readiness`, which UI-020
shows a reviewer before anything else.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from urllib.parse import urlparse

from app.agents.automation.generation_contract import AutomationGenerationContract
from app.services.recorder.context import RecordingContext
from app.services.recorder import steps as recorder_steps
from app.services.script_compiler.naming import slugify

# The contract's EnvironmentProfile vocabulary. A session environment outside
# it is reported rather than silently coerced.
CONTRACT_ENVIRONMENTS = ("DEV", "SIT", "QA", "UAT", "PREPROD", "PROD_SANITY")

FRAMEWORK_SCRIPT_TYPES = {
    "playwright": "playwright-typescript",
    "pytest": "pytest-python",
}

# Recorded action family -> contract StepAction.
ACTION_STEP_ACTIONS = {
    "navigate": "navigate",
    "click": "click",
    "input": "fill",
}

# Checkpoint type -> (contract AssertionType, needs_element_target).
# A type absent from this map cannot be expressed as an assertion in contract
# v1.0; it is preserved on the recording and reported in `readiness`.
CHECKPOINT_ASSERTIONS = {
    "element_visible": ("visible", True),
    "text_equals": ("text", True),
    "text_contains": ("text", True),
    "value_equals": ("value", True),
    "url_matches": ("url", False),
}

# locator_ranking's strategies are already the contract's vocabulary; this
# map exists so a future strategy cannot silently become an invalid one.
LOCATOR_STRATEGIES = {
    "role": "role",
    "testid": "testid",
    "label": "label",
    "placeholder": "placeholder",
    "text": "text",
    "css": "css",
    "xpath": "xpath",
}


@dataclass
class EmissionResult:
    contract: AutomationGenerationContract
    source_action_ids: list[int]
    readiness: dict = field(default_factory=dict)


def _page_object_name(page_url: str | None) -> str:
    if not page_url:
        return "AppPage"
    parsed = urlparse(page_url)
    path = (parsed.path or "").strip("/")
    base = slugify(path.replace("/", " ")) if path else slugify(parsed.netloc or "app")
    name = "".join(part.capitalize() for part in base.replace("-", "_").split("_") if part)
    return f"{name or 'App'}Page"


def _safe_identifier(value: str, fallback: str) -> str:
    candidate = slugify(value).replace("-", "_") if value else ""
    if not candidate or not candidate[0].isalpha() and candidate[0] != "_":
        candidate = f"el_{candidate}" if candidate else fallback
    return candidate[:64]


class _PageObjectBuilder:
    """Collects page objects and elements as actions are walked, keeping
    element names unique within each page object (the contract validates that
    every `Page.element` target resolves)."""

    def __init__(self) -> None:
        self._pages: dict[str, dict] = {}

    def add_element(self, *, page_url: str | None, element_name: str, strategy: str, value: str, role: str | None) -> str | None:
        page_name = _page_object_name(page_url)
        page = self._pages.setdefault(
            page_name,
            {"name": page_name, "route": urlparse(page_url).path if page_url else None, "elements": {}},
        )
        base = _safe_identifier(element_name, "element")
        locator_key = (strategy, value)

        for existing_name, existing in page["elements"].items():
            if (existing["locator_strategy"], existing["locator_value"]) == locator_key:
                return f"{page_name}.{existing_name}"

        name = base
        suffix = 2
        while name in page["elements"]:
            name = f"{base}_{suffix}"
            suffix += 1

        page["elements"][name] = {
            "name": name,
            "locator_strategy": strategy,
            "locator_value": value,
            "role_hint": role if strategy == "role" else None,
        }
        return f"{page_name}.{name}"

    def as_contract_pages(self) -> list[dict]:
        return [
            {
                "name": page["name"],
                "route": page["route"],
                "elements": list(page["elements"].values()),
            }
            for page in self._pages.values()
        ]


def _accepted_locator(action) -> tuple[str, str, str | None, str | None] | None:
    """(strategy, value, role, page_url) of the highest-ranked observed
    locator, or None when nothing was observed for this action."""
    evidence = action.locator_evidence or {}
    candidates = evidence.get("candidates") or []
    for candidate in candidates:
        strategy = LOCATOR_STRATEGIES.get(candidate.get("strategy"))
        value = candidate.get("value")
        if strategy and value:
            return strategy, value, evidence.get("role"), evidence.get("page_url")
    return None


def _environment_profile(environment: str | None) -> tuple[str, str | None]:
    normalized = (environment or "").strip().upper().replace(" ", "_")
    if normalized in CONTRACT_ENVIRONMENTS:
        return normalized, None
    return (
        "QA",
        f"Environment '{environment}' is not one of the Automation IR's environment profiles "
        f"({', '.join(CONTRACT_ENVIRONMENTS)}). The draft records QA; correct it in the IR Editor "
        "before generating a script.",
    )


def build(context: RecordingContext) -> EmissionResult:
    """Emits the IR draft for one recording. Pure — no database access."""
    session = context.session
    test_case = context.test_case
    unresolved: list[dict] = []

    mapping_by_action = context.mapping_by_action_id
    bindings_by_action = {b.action_id: b for b in context.bindings if b.action_id is not None}

    builder = _PageObjectBuilder()
    contract_steps: list[dict] = []
    cleanup_actions: list[dict] = []
    source_action_ids: list[int] = []
    element_ref_by_action: dict[int, str] = {}

    step_list = {s.step_key: s for s in recorder_steps.build_step_list(context)}

    for action in context.actions:
        if action.inclusion_state != "included":
            continue
        if action.action_family == "read":
            # An explicit observation the user made. It has no automated
            # counterpart and is not a gap — it is how a person checked state.
            continue

        mapping = mapping_by_action.get(action.id)
        if mapping is not None and mapping.excluded_from_ir:
            continue
        if mapping is None:
            unresolved.append(
                {
                    "kind": "unmapped_action",
                    "action_id": action.id,
                    "sequence": action.sequence,
                    "detail": f"Action #{action.sequence} ({action.action_family}) is not mapped to a "
                              "test case step and is not included in the IR.",
                }
            )
            continue

        step_action = ACTION_STEP_ACTIONS.get(action.action_family)
        recorder_step = step_list.get(mapping.step_key)
        expected = recorder_step.expected_result if recorder_step else None

        binding = bindings_by_action.get(action.id)
        target_ref: str | None = None

        if action.action_family in ("click", "input"):
            locator = _accepted_locator(action)
            if locator is None:
                unresolved.append(
                    {
                        "kind": "no_locator",
                        "action_id": action.id,
                        "sequence": action.sequence,
                        "detail": f"Action #{action.sequence} ({action.action_family} on "
                                  f"'{action.target_semantic}') has no observed locator candidate. "
                                  "Emitted as a custom step for manual completion.",
                    }
                )
                step_action = "custom"
            else:
                strategy, value, role, page_url = locator
                target_ref = builder.add_element(
                    page_url=page_url,
                    element_name=(action.locator_evidence or {}).get("element_name") or action.target_semantic or "element",
                    strategy=strategy,
                    value=value,
                    role=role,
                )
                element_ref_by_action[action.id] = target_ref

        phase = "arrange" if mapping.lifecycle_phase == "setup" else "act"

        if mapping.lifecycle_phase == "teardown":
            cleanup_actions.append(
                {
                    "type": "ui_action",
                    "description": action.target_semantic or f"Recorded teardown action #{action.sequence}",
                    "target": target_ref,
                }
            )
            source_action_ids.append(action.id)
            continue

        step: dict = {
            "phase": phase,
            "action": step_action or "custom",
            "target": target_ref,
            "expected_result": expected,
        }

        if step["action"] == "navigate":
            url = (action.input_binding or {}).get("url")
            step["value"] = url
            step["target"] = None
            if not url:
                step["action"] = "custom"
                step["description"] = action.target_semantic or "Recorded navigation with no captured URL"
                unresolved.append(
                    {
                        "kind": "navigate_without_url",
                        "action_id": action.id,
                        "sequence": action.sequence,
                        "detail": f"Action #{action.sequence} was a navigation but no URL was captured.",
                    }
                )
        elif step["action"] == "fill":
            if binding is not None:
                step["data_binding"] = binding.name
            else:
                text = (action.input_binding or {}).get("text")
                step["value"] = text
                if text:
                    unresolved.append(
                        {
                            "kind": "unbound_input",
                            "action_id": action.id,
                            "sequence": action.sequence,
                            "detail": f"Action #{action.sequence} types a literal value that has not been "
                                      "classified as test data, a secret or a runtime value. It will be "
                                      "hard-coded in the generated script.",
                        }
                    )
        elif step["action"] == "custom":
            step.setdefault(
                "description",
                action.target_semantic or f"Recorded {action.action_family} action #{action.sequence}",
            )

        contract_steps.append(step)
        source_action_ids.append(action.id)

    # ── Assertions from accepted checkpoints only (Section 16) ──
    assertions: list[dict] = []
    for checkpoint in context.checkpoints:
        if checkpoint.review_state != "accepted":
            if checkpoint.source == "recommended":
                unresolved.append(
                    {
                        "kind": "unreviewed_recommendation",
                        "checkpoint_id": checkpoint.id,
                        "detail": f"Recommended checkpoint '{checkpoint.checkpoint_type}' has not been "
                                  "reviewed and is not asserted.",
                    }
                )
            continue

        mapped = CHECKPOINT_ASSERTIONS.get(checkpoint.checkpoint_type)
        if mapped is None:
            unresolved.append(
                {
                    "kind": "unrenderable_checkpoint",
                    "checkpoint_id": checkpoint.id,
                    "detail": f"Checkpoint type '{checkpoint.checkpoint_type}' has no equivalent in "
                              "Automation IR v1.0 and is recorded but not asserted.",
                }
            )
            continue

        assertion_type, needs_element = mapped
        if needs_element:
            target = element_ref_by_action.get(checkpoint.action_id) if checkpoint.action_id else None
            if target is None:
                unresolved.append(
                    {
                        "kind": "checkpoint_without_element",
                        "checkpoint_id": checkpoint.id,
                        "detail": f"Checkpoint '{checkpoint.checkpoint_type}' is not attached to an action "
                                  "with an observed locator, so it cannot target an element.",
                    }
                )
                continue
        else:
            target = "page"

        assertions.append(
            {
                "type": assertion_type,
                "target": target,
                "expected": checkpoint.expected_value or "",
                "web_first": True,
            }
        )

    # ── Test data bindings (Section 18) ──
    test_data_bindings = [
        {
            "name": binding.name,
            "placeholder": binding.placeholder,
            # A secret is referenced, never valued — Section 18.
            "fallback": None if binding.classification == "secret_reference" else binding.sample_value,
        }
        for binding in context.bindings
    ]
    for binding in context.bindings:
        if binding.classification == "secret_reference":
            unresolved.append(
                {
                    "kind": "secret_reference",
                    "detail": f"'{binding.name}' resolves from secret '{binding.secret_reference}' at run "
                              "time. Make sure that secret exists in the execution environment.",
                }
            )

    environment_profile, environment_note = _environment_profile(session.environment)
    if environment_note:
        unresolved.append({"kind": "environment_profile", "detail": environment_note})

    script_type = FRAMEWORK_SCRIPT_TYPES.get(session.framework)
    if script_type is None:
        script_type = "playwright-typescript"
        unresolved.append(
            {
                "kind": "script_type",
                "detail": f"Framework '{session.framework}' has no Automation IR script type. The draft "
                          "records playwright-typescript; correct it in the IR Editor.",
            }
        )

    expected_results = [
        step.expected_result for step in step_list.values() if step.expected_result and step.status != "SKIPPED"
    ]
    preconditions = [
        str(p) for p in ((test_case.preconditions if test_case else None) or []) if str(p).strip()
    ]

    evidence_required = sorted({c.capture_type for c in context.captures})

    contract = AutomationGenerationContract.model_validate(
        {
            "contractVersion": "1.0",
            "testCaseId": test_case.test_case_id if test_case else f"recording-{session.id}",
            "requirementId": session.requirement_ref,
            "testType": (test_case.test_type if test_case and test_case.test_type else "functional"),
            "scriptType": script_type,
            "environmentProfile": environment_profile,
            "businessFlow": test_case.title if test_case else "",
            "preconditions": preconditions,
            "testDataBindings": test_data_bindings,
            "pageObjects": builder.as_contract_pages(),
            "steps": contract_steps,
            "expectedResults": expected_results,
            "assertions": assertions,
            "cleanupActions": cleanup_actions,
            "evidenceRequired": evidence_required,
        }
    )

    readiness = {
        "unresolved": unresolved,
        "unresolved_count": len(unresolved),
        "step_count": len(contract_steps),
        "assertion_count": len(assertions),
        "custom_step_count": sum(1 for s in contract_steps if s["action"] == "custom"),
        # Not a pass/fail gate: a draft with open items is still worth
        # producing, and UI-020 is where they get resolved.
        "ready_for_script_generation": not unresolved and bool(contract_steps),
    }

    return EmissionResult(contract=contract, source_action_ids=source_action_ids, readiness=readiness)
