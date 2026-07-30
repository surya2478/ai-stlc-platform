"""UI-020 IR Editor — loading, validating and saving the Automation IR.

The validation boundary is `AutomationGenerationContract.model_validate`, and it
is deliberately the *only* one. Section 11.4 of the contract requires the editor
to validate on every edit rather than on save, so this module exposes
`validate_contract` (no writes, real pydantic errors, structured per field) and
`save_contract` (validates first, then persists). Both go through the same
model, so the Advanced JSON surface and the structured form cannot diverge.

Element sourcing for the picker comes from the approved Application Model
(UI-016), never from free text — an element the recorder observed but the model
does not contain is offered with `in_model: false` so the UI can label it
"recorded, not in model" instead of silently promoting it.
"""
from __future__ import annotations

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.automation.generation_contract import (
    ELEMENT_REQUIRED_ACTIONS_TUPLE,
    AutomationGenerationContract,
)
from app.models.application_model import (
    ApplicationModel,
    ApplicationModelLocatorEvidence,
    ApplicationModelNode,
)
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.locator_map import LocatorMapEntry
from app.models.recording_session import AutomationIrDraft
from app.services.automation_suite.errors import AutomationSuiteError


def _field_path(error: dict) -> str:
    """A dotted path the UI can anchor an inline message to.

    Pydantic reports `('steps', 3, 'target')`; the editor needs
    `steps.3.target` so it can highlight the offending row rather than showing
    a page-level error.
    """
    parts = [str(p) for p in error.get("loc", ()) if p != "__root__"]
    return ".".join(parts)


def _target_anchors(payload: dict) -> list[dict]:
    """Field-anchored errors for unresolvable targets.

    `_targets_resolve_to_real_elements` is a model-level validator, so pydantic
    reports it with an empty `loc` — the message names the bad target but not
    which row holds it. Section 11.4 requires the error to appear inline against
    the offending row, so this reproduces the same rule positionally.

    It is a supplement, never a replacement: the pydantic message stays
    authoritative, and anything this misses still surfaces at page level rather
    than being swallowed.
    """
    valid_refs = {
        f"{page.get('name')}.{element.get('name')}"
        for page in (payload.get("pageObjects") or [])
        for element in (page.get("elements") or [])
    }
    element_required = set(ELEMENT_REQUIRED_ACTIONS_TUPLE)
    anchors: list[dict] = []

    def bad(target, *, required: bool) -> str | None:
        if target is None:
            return "This action needs a specific element." if required else None
        if target == "page":
            return "'page' is only valid for url assertions — pick a specific element."
        if "." not in target:
            return f"'{target}' is not a <PageObject>.<element> reference."
        if target not in valid_refs:
            return f"'{target}' does not match any declared page object element."
        return None

    for index, step in enumerate(payload.get("steps") or []):
        action = step.get("action")
        if action in ("navigate", "custom", "wait_for_url"):
            continue
        message = bad(step.get("target"), required=action in element_required)
        if message:
            anchors.append(
                {"field": f"steps.{index}.target", "message": message, "type": "value_error"}
            )

    for index, assertion in enumerate(payload.get("assertions") or []):
        if assertion.get("type") == "url":
            continue
        message = bad(assertion.get("target"), required=False)
        if message:
            anchors.append(
                {"field": f"assertions.{index}.target", "message": message, "type": "value_error"}
            )

    return anchors


def validate_contract(payload: dict) -> dict:
    """Validate without saving. Returns the structured result the editor renders.

    Never raises for a *content* problem — an invalid draft is a normal state
    while someone is mid-edit, and the editor needs the errors, not a 500.
    """
    try:
        contract = AutomationGenerationContract.model_validate(payload)
    except ValidationError as exc:
        errors = [
            {
                "field": _field_path(err),
                "message": err.get("msg", "Invalid value"),
                "type": err.get("type", "value_error"),
            }
            for err in exc.errors()
        ]
        # Model-level target errors arrive with an empty field, so the editor
        # cannot highlight a row. Where we can identify the row ourselves,
        # swap them for anchored equivalents. If we cannot, the original
        # unanchored error is kept — never dropped.
        anchors = _target_anchors(payload)
        if anchors:
            errors = [
                e for e in errors if e["field"] or "target" not in e["message"]
            ] + anchors
        return {"valid": False, "errors": errors, "summary": None}

    custom = [i for i, s in enumerate(contract.steps) if s.action == "custom"]
    return {
        "valid": True,
        "errors": [],
        "summary": {
            "step_count": len(contract.steps),
            "custom_step_count": len(custom),
            "custom_step_indexes": custom,
            "locator_count": len(contract.all_locators),
            "assertion_count": len(contract.assertions),
            "page_object_count": len(contract.page_objects),
            "binding_count": len(contract.test_data_bindings),
            # The IR Editor's exit condition (Section 11.9): a contract that
            # validates AND has no custom steps left.
            "ready_for_compile": not custom,
        },
    }


async def current_draft(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> AutomationIrDraft | None:
    result = await db.execute(
        select(AutomationIrDraft)
        .where(
            AutomationIrDraft.suite_id == suite.id,
            AutomationIrDraft.test_case_id == member.test_case_id,
            AutomationIrDraft.is_current.is_(True),
        )
        .order_by(AutomationIrDraft.version.desc(), AutomationIrDraft.id.desc())
        .limit(1)
    )
    return result.scalars().first()


async def list_versions(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> list[AutomationIrDraft]:
    """The version chain of the *current* draft.

    `is_current` is scoped to one recording session's chain, not to the member:
    recording the same test case three times produces three independent chains,
    each with its own current v1. Listing every draft for the member therefore
    showed three unrelated rows all marked current, which reads as corruption.
    The chain is the drafts sharing the current draft's `session_id`.
    """
    current = await current_draft(db, member, suite)
    if current is None:
        return []
    result = await db.execute(
        select(AutomationIrDraft)
        .where(AutomationIrDraft.session_id == current.session_id)
        .order_by(AutomationIrDraft.version.desc(), AutomationIrDraft.id.desc())
    )
    return list(result.scalars().all())


async def count_other_session_drafts(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> int:
    """Drafts for this member produced by *other* recording sessions.

    Surfaced as a count rather than merged into the chain, so a user who
    recorded the same test case more than once can see that other drafts exist
    without them masquerading as versions of this one.
    """
    current = await current_draft(db, member, suite)
    if current is None:
        return 0
    result = await db.execute(
        select(AutomationIrDraft).where(
            AutomationIrDraft.suite_id == suite.id,
            AutomationIrDraft.test_case_id == member.test_case_id,
            AutomationIrDraft.session_id != current.session_id,
        )
    )
    return len(list(result.scalars().all()))


def _recompute_readiness(existing: dict | None, contract: AutomationGenerationContract) -> dict:
    """Refresh only the counts a human edit can change.

    `unresolved[]` itself is the emitter's output and is NOT regenerated here:
    this module cannot re-observe a browser, so inventing or dropping entries
    would fabricate provenance. Entries are removed only when the edit
    demonstrably resolves them — which today means the caller clearing them
    explicitly, not this function guessing.
    """
    readiness = dict(existing or {})
    readiness["step_count"] = len(contract.steps)
    readiness["assertion_count"] = len(contract.assertions)
    readiness["custom_step_count"] = sum(1 for s in contract.steps if s.action == "custom")
    unresolved = readiness.get("unresolved") or []
    readiness["unresolved"] = unresolved
    readiness["unresolved_count"] = len(unresolved)
    readiness["ready_for_script_generation"] = (
        not unresolved and bool(contract.steps) and readiness["custom_step_count"] == 0
    )
    return readiness


async def save_contract(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
    *,
    payload: dict,
    actor_id: int,
    resolved_readiness_kinds: list[str] | None = None,
) -> tuple[AutomationIrDraft, dict]:
    """Persist an edited contract.

    Editing a draft that has not yet produced a script edits it in place.
    Editing one that has creates version n+1 and supersedes the prior, so the
    IR that produced a compiled script is never mutated out from under it
    (Section 11.8, the same discipline `parent_script_id` gives scripts).

    `resolved_readiness_kinds` lets the editor state which readiness entries an
    edit resolved. Nothing is inferred: an entry disappears because the user
    resolved it through an affordance that says so, never because a heuristic
    decided it looked fixed.
    """
    result = validate_contract(payload)
    if not result["valid"]:
        raise AutomationSuiteError(
            422,
            "IR_VALIDATION_FAILED",
            "; ".join(f"{e['field']}: {e['message']}" for e in result["errors"][:5]),
        )

    contract = AutomationGenerationContract.model_validate(payload)
    normalized = contract.model_dump(by_alias=True)

    draft = await current_draft(db, member, suite)
    if draft is None:
        raise AutomationSuiteError(
            404,
            "NO_IR_DRAFT",
            "This asset has no Automation IR yet. Record it in the Live Recorder "
            "or generate it before editing.",
        )

    readiness = _recompute_readiness(draft.readiness, contract)
    if resolved_readiness_kinds:
        remaining = [
            item
            for item in (readiness.get("unresolved") or [])
            if item.get("kind") not in set(resolved_readiness_kinds)
        ]
        readiness["unresolved"] = remaining
        readiness["unresolved_count"] = len(remaining)
        readiness["ready_for_script_generation"] = (
            not remaining and bool(contract.steps) and readiness["custom_step_count"] == 0
        )

    # Has this IR already produced a script? If so it is contracted, and an
    # edit opens a new version rather than rewriting history.
    if member.resolved_script_id is not None:
        draft.is_current = False
        draft.status = "SUPERSEDED"
        new_draft = AutomationIrDraft(
            project_id=draft.project_id,
            session_id=draft.session_id,
            suite_id=draft.suite_id,
            test_case_id=draft.test_case_id,
            version=draft.version + 1,
            is_current=True,
            status="DRAFT",
            contract=normalized,
            contract_version=contract.contract_version,
            source_action_ids=list(draft.source_action_ids or []),
            readiness=readiness,
            generated_by=actor_id,
        )
        db.add(new_draft)
        await db.flush()
        return new_draft, result

    draft.contract = normalized
    draft.contract_version = contract.contract_version
    draft.readiness = readiness
    await db.flush()
    return draft, result


# ── Element catalogue for the picker (Section 11.5) ──────────────────────────


async def element_catalogue(
    db: AsyncSession, *, project_id: int, application_id: int | None, draft: AutomationIrDraft | None
) -> dict:
    """Elements the picker may offer, each labelled with where it came from.

    Three sources, never merged into an anonymous list:
      - the approved Application Model (UI-016) — the authoritative catalogue
      - the locator map — elements with live grounding evidence
      - the draft's own declared page objects — already in this contract

    An element present only in the draft is returned with `in_model: false` so
    the UI can show "recorded, not in model" and offer to propose it into the
    model, rather than presenting unmodelled elements as approved.
    """
    catalogue: dict[str, dict] = {}

    if application_id is not None:
        model_row = (
            await db.execute(
                select(ApplicationModel)
                .where(
                    ApplicationModel.project_id == project_id,
                    ApplicationModel.application_id == application_id,
                    # APPLICATION_MODEL_STATUSES are lowercase. Filtering on
                    # uppercase here silently matched nothing, which made every
                    # element look ungrounded — a false negative, not an error.
                    ApplicationModel.status.in_(("approved", "published")),
                )
                .order_by(ApplicationModel.version.desc())
                .limit(1)
            )
        ).scalars().first()

        if model_row is not None:
            nodes = (
                await db.execute(
                    select(ApplicationModelNode).where(
                        ApplicationModelNode.model_id == model_row.id,
                        ApplicationModelNode.node_type == "element",
                    )
                )
            ).scalars().all()
            for node in nodes:
                evidence = (
                    await db.execute(
                        select(ApplicationModelLocatorEvidence)
                        .where(ApplicationModelLocatorEvidence.node_id == node.id)
                        .order_by(ApplicationModelLocatorEvidence.id.desc())
                        .limit(1)
                    )
                ).scalars().first()
                catalogue[node.display_name] = {
                    "name": node.display_name,
                    "source": "application_model",
                    "in_model": True,
                    "locator_value": evidence.locator_value if evidence else None,
                    "locator_strategy": evidence.locator_type if evidence else None,
                    "confidence": evidence.confidence if evidence else None,
                    "business_meaning": node.description,
                }

        for entry in (
            await db.execute(
                select(LocatorMapEntry).where(
                    LocatorMapEntry.project_id == project_id,
                    LocatorMapEntry.application_id == application_id,
                )
            )
        ).scalars().all():
            existing = catalogue.get(entry.element_name)
            if existing is None:
                catalogue[entry.element_name] = {
                    "name": entry.element_name,
                    "source": "locator_map",
                    "in_model": False,
                    "locator_value": entry.recommended_locator,
                    "locator_strategy": entry.recommended_strategy,
                    "confidence": entry.confidence_score,
                    "business_meaning": entry.business_meaning,
                }
            elif existing.get("confidence") is None:
                existing["confidence"] = entry.confidence_score

    declared: list[dict] = []
    if draft is not None:
        for page_object in (draft.contract or {}).get("pageObjects") or []:
            for element in page_object.get("elements") or []:
                name = element.get("name")
                declared.append(
                    {
                        "page_object": page_object.get("name"),
                        "name": name,
                        "locator_strategy": element.get("locatorStrategy"),
                        "locator_value": element.get("locatorValue"),
                        "role_hint": element.get("roleHint"),
                        "nth": element.get("nth"),
                        "business_meaning": element.get("businessMeaning"),
                        "in_model": name in catalogue and catalogue[name]["in_model"],
                    }
                )

    return {
        # Declared elements are what a step target may reference today — the
        # picker's primary list, because a target must resolve to one of these
        # or the contract will not validate.
        "declared": declared,
        # Everything the platform knows about, for adding to the contract.
        "available": sorted(catalogue.values(), key=lambda e: e["name"]),
        "element_required_actions": list(ELEMENT_REQUIRED_ACTIONS_TUPLE),
    }
