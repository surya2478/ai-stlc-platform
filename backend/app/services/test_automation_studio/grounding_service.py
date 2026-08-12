"""Bind refined test case steps to elements discovery actually found.

This is the step that makes the difference between a script that reads well
and a script that runs. A refined test case says `target: "Login button"`;
the discovered catalog says the real control is
`getByRole('link', { name: 'Continue' })`. Matching the two is what turns a
description into a locator, and — just as importantly — reporting the ones
that do NOT match is what stops the generator inventing a locator for a
control nobody has ever seen.

Deliberately deterministic: no LLM anywhere in this file. Matching a step's
target against a catalog of accessible names is string work, and running it
through a model would make the result unreproducible, slow, and impossible
to explain on the drawer that shows a user why their step did not resolve.
Every unresolved step therefore carries a `reason` a human can act on.

The output is advisory, not a gate. An ungrounded test case can still be
approved and still have a script generated — it simply produces a script
whose locators are guesses, which is exactly what the badge on Screen 2 is
there to warn about.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.test_automation_studio import TasRefinedTestCase
from app.services.test_automation_studio import discovery_service

# What a step's verb implies about the element's ARIA role. A step saying
# "enter the username" cannot be satisfied by a button, no matter how well
# the words overlap — role affinity is what keeps a high text score from
# matching the wrong kind of control.
_ROLE_AFFINITY: tuple[tuple[tuple[str, ...], frozenset[str]], ...] = (
    (
        ("enter", "type", "input", "fill", "key in", "provide", "populate"),
        frozenset({"textbox", "searchbox", "combobox", "spinbutton"}),
    ),
    (("select", "choose", "pick"), frozenset({"combobox", "listbox", "option", "menuitem"})),
    (("check", "tick", "toggle"), frozenset({"checkbox", "switch", "radio"})),
    (("uncheck", "untick"), frozenset({"checkbox", "switch"})),
    (("click", "press", "tap", "submit", "confirm"), frozenset({"button", "link", "menuitem", "tab"})),
)

# Steps whose verb needs no element at all. Left out of the score entirely
# rather than counted as failures — reporting "navigate to the home page" as
# an unresolved locator would bury the gaps that actually matter.
_NON_ELEMENT_VERBS = (
    "navigate", "go to", "open the", "launch", "wait", "observe", "note",
    "ensure that", "confirm that", "the system", "user is", "log out and",
)

_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "on", "in", "to", "for", "with",
    "button", "field", "link", "icon", "box", "input", "page", "screen",
    "click", "enter", "type", "select", "press", "valid", "user", "users",
})

# Below this, a match is a coincidence. Two shared meaningful words is the
# smallest overlap that reliably distinguished a real match from a wrong one
# on the batches this was built against; one word matches "Search" against
# "Search results heading" as readily as against the search box.
_MIN_SCORE = 2

_WORD_RE = re.compile(r"[^a-z0-9]+")


def _tokens(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        word
        for word in _WORD_RE.split(text.lower())
        if len(word) > 2 and word not in _STOPWORDS
    }


def _normalized(text: str | None) -> str:
    return " ".join(sorted(_tokens(text)))


def _affine_roles(action: str) -> frozenset[str]:
    lowered = (action or "").lower()
    for verbs, roles in _ROLE_AFFINITY:
        if any(verb in lowered for verb in verbs):
            return roles
    return frozenset()


def _needs_element(step: dict) -> bool:
    """Whether this step is expected to touch a specific control."""
    if not (step.get("target") or "").strip():
        return False
    action = (step.get("action") or "").lower()
    return not any(verb in action for verb in _NON_ELEMENT_VERBS)


def _score(step_tokens: set[str], entry: dict) -> int:
    """Overlap between the step's words and everything known about an element.

    The accessible name is weighted double: it is what the locator will
    actually match on, whereas business meaning is a label an LLM attached
    during discovery and element_name is a slug derived from the other two.
    """
    name_overlap = len(step_tokens & _tokens(entry.get("accessible_name")))
    other_overlap = len(
        step_tokens & (_tokens(entry.get("business_meaning")) | _tokens(entry.get("element_name")))
    )
    return name_overlap * 2 + other_overlap


def match_step(step: dict, catalog: list[dict]) -> tuple[dict | None, str | None]:
    """Best catalog entry for one step, or (None, reason).

    Role affinity narrows the field first; when nothing of the right role
    matches, the whole catalog is retried so a step whose verb was phrased
    unusually still has a chance — but a match found that way has to clear
    the same score bar.
    """
    target = (step.get("target") or "").strip()
    step_tokens = _tokens(target) | _tokens(step.get("action"))
    if not step_tokens:
        return None, "The step names no target to match against."

    exact = _normalized(target)
    roles = _affine_roles(step.get("action") or "")

    def _search(pool: list[dict]) -> tuple[dict | None, str | None]:
        if not pool:
            return None, None
        for entry in pool:
            if exact and _normalized(entry.get("accessible_name")) == exact:
                return entry, None
        ranked = sorted(pool, key=lambda e: (-_score(step_tokens, e), -int(e.get("confidence_score") or 0)))
        best = ranked[0]
        best_score = _score(step_tokens, best)
        if best_score < _MIN_SCORE:
            return None, None
        runners_up = [e for e in ranked[1:] if _score(step_tokens, e) == best_score]
        if runners_up:
            names = ", ".join(
                f'"{e.get("accessible_name") or e.get("element_name")}"' for e in [best, *runners_up[:2]]
            )
            return None, (
                f"Matches more than one discovered element equally well ({names}). "
                "Make the step's target more specific."
            )
        return best, None

    if roles:
        entry, reason = _search([e for e in catalog if (e.get("role") or "") in roles])
        if entry is not None or reason is not None:
            return entry, reason

    entry, reason = _search(catalog)
    if entry is not None:
        return entry, None
    if reason is not None:
        return None, reason
    return None, (
        f'No discovered element matches "{target}". Either the page holding it was not '
        "crawled, or it renders with a different label than the test case expects."
    )


def ground_test_case(test_case: TasRefinedTestCase, catalog: list[dict]) -> dict:
    """The grounding summary for one test case. Pure — no I/O, no mutation."""
    steps = test_case.steps or []
    matched: list[dict] = []
    unresolved: list[dict] = []
    skipped = 0

    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            continue
        step_number = step.get("step_number") or (index + 1)
        if not _needs_element(step):
            skipped += 1
            continue
        entry, reason = match_step(step, catalog)
        if entry is None:
            unresolved.append(
                {
                    "step_number": step_number,
                    "action": step.get("action"),
                    "target": step.get("target"),
                    "reason": reason or "No matching element was discovered.",
                }
            )
            continue
        matched.append(
            {
                "step_number": step_number,
                "target": step.get("target"),
                "element_name": entry.get("element_name"),
                "locator": entry.get("recommended_locator"),
                "page": entry.get("page"),
                "confidence": entry.get("confidence_score"),
            }
        )

    groundable = len(matched) + len(unresolved)
    if groundable == 0:
        status = "ungrounded"
        note = (
            "No step in this test case names a UI control, so there is nothing to match "
            "against the discovered application."
        )
    elif not unresolved:
        status = "grounded"
        note = None
    elif matched:
        status = "partially_grounded"
        note = None
    else:
        status = "ungrounded"
        note = None

    return {
        "status": status,
        "summary": {
            "total_steps": len(steps),
            "groundable_steps": groundable,
            "matched_steps": len(matched),
            "skipped_steps": skipped,
            "matched": matched,
            "unresolved": unresolved,
            "note": note,
        },
    }


async def ground_batch(
    db: AsyncSession,
    *,
    project_id: int,
    test_case_ids: list[int] | None = None,
    batch_id: int | None = None,
) -> tuple[list[TasRefinedTestCase], list[dict]]:
    """Ground a selection of refined test cases against their batch's catalog.

    Grouped by batch because the catalog is per batch: two batches in one
    project may point at different applications entirely, and grounding a
    test case against the wrong application's elements would produce
    confident, wrong matches.
    """
    query = select(TasRefinedTestCase).where(TasRefinedTestCase.project_id == project_id)
    if test_case_ids:
        query = query.where(TasRefinedTestCase.id.in_(test_case_ids))
    if batch_id is not None:
        query = query.where(TasRefinedTestCase.batch_id == batch_id)
    test_cases = list((await db.execute(query)).scalars().all())

    updated: list[TasRefinedTestCase] = []
    skipped: list[dict] = []
    catalogs: dict[int, tuple[object, list[dict]]] = {}

    for test_case in test_cases:
        if test_case.batch_id is None:
            skipped.append(
                {
                    "test_case_id": test_case.id,
                    "tc_display_id": test_case.tc_display_id,
                    "reason": "Not linked to an intake batch, so it has no application to ground against.",
                }
            )
            continue
        if test_case.batch_id not in catalogs:
            catalogs[test_case.batch_id] = await discovery_service.current_catalog(
                db, test_case.batch_id
            )
        run, catalog = catalogs[test_case.batch_id]
        if run is None or not catalog:
            skipped.append(
                {
                    "test_case_id": test_case.id,
                    "tc_display_id": test_case.tc_display_id,
                    "reason": "No completed discovery run for this batch — run Discover Application first.",
                }
            )
            continue

        result = ground_test_case(test_case, catalog)
        test_case.grounding_status = result["status"]
        test_case.grounding_summary = {**result["summary"], "discovery_run_id": run.id}
        test_case.grounded_at = datetime.now(timezone.utc)
        test_case.discovery_run_id = run.id
        db.add(test_case)
        updated.append(test_case)

    await db.commit()
    for test_case in updated:
        await db.refresh(test_case)
    return updated, skipped
