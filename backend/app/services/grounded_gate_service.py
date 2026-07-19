"""Grounded Automation PoC — deterministic four-dimension coverage gate.

The "no guesswork" enforcer. After capture, every TC step must be grounded
across four dimensions before generation is allowed:

  action    — the step's target element exists in a captured Application
              State Evidence Package (or the step is pure navigation to a
              captured state)
  data      — the input values the step needs exist in the TC's test_data
              (or the step needs no data)
  assertion — the expected result has a verified validation channel: its
              text is observable in captured evidence (UI channel), or it
              routes to a non-UI adapter (then it is a gap until that
              adapter ships — never silently skipped)
  cleanup   — mutating steps note a rollback path (warning-level in the
              PoC: recorded and surfaced, does not block generation alone)

100% *required* evidence coverage — not just screen coverage — is the rule:
generation_allowed is True only when every step's action/data/assertion
dimensions are covered. No LLM anywhere in this module, by design: a gate
that can hallucinate is not a gate.
"""
from __future__ import annotations

import re
from typing import Any

from app.services.grounded_routing_service import _step_texts

_WORD_RE = re.compile(r"[a-z0-9]+")
# Words too generic to indicate a match on their own.
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "then", "click", "select",
    "enter", "verify", "check", "page", "button", "field", "user", "should",
    "will", "into", "from", "value", "valid", "invalid", "displayed", "shown",
    "screen", "open", "navigate", "launch", "goto", "are", "is", "be", "on", "in",
})
# Steps that only move to a page — grounded by the *state* being captured,
# not by any single element.
_NAVIGATION_RE = re.compile(r"\b(navigate|open|launch|go\s*to|visit|access)\b", re.IGNORECASE)
# Steps that need input data.
_DATA_ENTRY_RE = re.compile(r"\b(enter|fill|type|input|provide|search\s+for|select)\b", re.IGNORECASE)

MIN_MATCH_SCORE = 1  # ≥1 significant shared token — snapshot names are short


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2 and w not in _STOPWORDS}


def _best_element_match(step_tokens: set[str], evidence_packages: list[dict]) -> dict | None:
    """Find the evidence element whose accessible name best overlaps the
    step text. Returns {"evidence_id", "state_fingerprint", "element_name",
    "recommended_locator", "score"} or None."""
    best: dict | None = None
    for pkg in evidence_packages:
        for el in pkg.get("elements") or []:
            name_tokens = _tokens(str(el.get("accessible_name") or el.get("element_name") or ""))
            if not name_tokens:
                continue
            score = len(step_tokens & name_tokens)
            if score >= MIN_MATCH_SCORE and (best is None or score > best["score"]):
                best = {
                    "evidence_id": pkg.get("id"),
                    "state_fingerprint": pkg.get("state_fingerprint"),
                    "element_name": el.get("element_name"),
                    "recommended_locator": el.get("recommended_locator"),
                    "score": score,
                }
    return best


def _assertion_in_snapshots(expected_tokens: set[str], evidence_packages: list[dict]) -> dict | None:
    """UI assertion channel: is the expected result observable in any
    captured state (element names or masked snapshot text)?"""
    if not expected_tokens:
        return None
    for pkg in evidence_packages:
        snapshot_tokens = _tokens(pkg.get("snapshot_text") or "")
        for el in pkg.get("elements") or []:
            snapshot_tokens |= _tokens(str(el.get("accessible_name") or ""))
        overlap = expected_tokens & snapshot_tokens
        # Require either full containment of a small assertion or a solid
        # overlap of a longer one.
        if overlap and (len(overlap) >= min(2, len(expected_tokens)) or len(overlap) >= len(expected_tokens) // 2 + 1):
            return {
                "evidence_id": pkg.get("id"),
                "state_fingerprint": pkg.get("state_fingerprint"),
                "matched_tokens": sorted(overlap)[:10],
            }
    return None


def _referenced_data_fields(action_text: str, test_data: dict | None) -> tuple[list[str], list[str]]:
    """(available, missing) test-data field names the step appears to need."""
    if not _DATA_ENTRY_RE.search(action_text):
        return [], []
    data = test_data or {}
    data_keys = {str(k).lower().replace("_", " "): str(k) for k in data.keys()}
    action_lower = action_text.lower()
    available = [orig for norm, orig in data_keys.items() if norm in action_lower or any(
        t in action_lower for t in norm.split() if len(t) > 3
    )]
    if available:
        return sorted(set(available)), []
    if data:
        # Data exists but no field name matched the step text — treat the
        # whole test_data dict as the binding (common: generic "enter test
        # data" phrasing). Available, flagged low-precision.
        return [f"{k} (unmatched binding)" for k in list(data.keys())[:10]], []
    return [], ["No test_data on the test case for a data-entry step"]


def evaluate_coverage(
    *,
    test_case: dict[str, Any],
    evidence_packages: list[dict[str, Any]],
    routing: dict[str, Any],
) -> dict[str, Any]:
    """Deterministic gate verdict. Stored on PocGroundingRun.coverage."""
    steps = test_case.get("steps") or []
    routing_steps = {r["index"]: r for r in (routing or {}).get("steps", [])}
    results: list[dict[str, Any]] = []
    unsupported: list[str] = []
    warnings: list[str] = []

    for index, raw_step in enumerate(steps):
        action_text, expected_text = _step_texts(raw_step)
        route = routing_steps.get(index, {})
        action_route = route.get("action_route") or {}
        assertion_route = route.get("assertion_route") or {}
        step_result: dict[str, Any] = {
            "step": index + 1,
            "action_text": action_text[:200],
            "action_evidence": None,
            "data_evidence": None,
            "assertion_evidence": None,
            "cleanup_evidence": None,
            "gaps": [],
            "status": "covered",
        }

        # ── Action grounding ───────────────────────────────────────────
        if action_route.get("type", "web_ui") == "web_ui":
            step_tokens = _tokens(action_text)
            if _NAVIGATION_RE.search(action_text) and evidence_packages:
                entry = evidence_packages[0]
                step_result["action_evidence"] = {
                    "kind": "captured_state",
                    "evidence_id": entry.get("id"),
                    "state_fingerprint": entry.get("state_fingerprint"),
                }
            else:
                match = _best_element_match(step_tokens, evidence_packages)
                if match:
                    step_result["action_evidence"] = {"kind": "captured_element", **match}
                else:
                    step_result["gaps"].append(
                        f"No captured element matches the action '{action_text[:80]}'"
                    )
        elif action_route.get("implemented"):
            step_result["action_evidence"] = {"kind": "adapter", "adapter": action_route.get("adapter")}
        else:
            gap = (
                f"Step routes to '{action_route.get('adapter')}' ({action_route.get('type')}) — "
                f"adapter not implemented in this PoC ({action_route.get('target_phase')})"
            )
            step_result["gaps"].append(gap)
            unsupported.append(f"step {index + 1}: {action_route.get('adapter')}")

        # ── Data grounding ─────────────────────────────────────────────
        available, missing = _referenced_data_fields(action_text, test_case.get("test_data"))
        if missing:
            step_result["gaps"].extend(missing)
        elif available:
            step_result["data_evidence"] = {"kind": "test_data_binding", "fields": available}
        else:
            step_result["data_evidence"] = {"kind": "not_required"}

        # ── Assertion grounding ────────────────────────────────────────
        if not expected_text.strip():
            step_result["assertion_evidence"] = {"kind": "not_required"}
        elif assertion_route.get("type", "web_ui") == "web_ui":
            found = _assertion_in_snapshots(_tokens(expected_text), evidence_packages)
            if found:
                step_result["assertion_evidence"] = {"kind": "captured_state_text", **found}
            else:
                step_result["gaps"].append(
                    f"Expected result '{expected_text[:80]}' was not observed in any captured state"
                )
        elif assertion_route.get("implemented"):
            step_result["assertion_evidence"] = {"kind": "adapter", "adapter": assertion_route.get("adapter")}
        else:
            gap = (
                f"Assertion needs '{assertion_route.get('adapter')}' ({assertion_route.get('type')}) — "
                f"adapter not implemented in this PoC ({assertion_route.get('target_phase')})"
            )
            step_result["gaps"].append(gap)
            unsupported.append(f"step {index + 1} assertion: {assertion_route.get('adapter')}")

        # ── Cleanup grounding (warning-level in PoC) ───────────────────
        if route.get("requires_cleanup"):
            preconditions = " ".join(str(p) for p in (test_case.get("preconditions") or []))
            if re.search(r"\b(cleanup|rollback|delete|revert|teardown)\b", preconditions, re.IGNORECASE):
                step_result["cleanup_evidence"] = {"kind": "declared_in_preconditions"}
            else:
                step_result["cleanup_evidence"] = None
                warnings.append(
                    f"Step {index + 1} mutates state but the test case declares no cleanup/rollback"
                )

        if step_result["gaps"]:
            step_result["status"] = "gap"
        results.append(step_result)

    covered = sum(1 for r in results if r["status"] == "covered")
    total = len(results)
    blockers = sorted({b for pkg in evidence_packages for b in (pkg.get("blockers") or [])})
    generation_allowed = total > 0 and covered == total and not blockers

    return {
        "testCaseId": test_case.get("test_case_id"),
        "overallCoverage": round(covered / total, 3) if total else 0.0,
        "coveredSteps": covered,
        "totalSteps": total,
        "steps": results,
        "unsupportedReferences": sorted(set(unsupported)),
        "liveBlockers": blockers,
        "warnings": warnings,
        "evidencePackageCount": len(evidence_packages),
        "generationAllowed": generation_allowed,
    }
