"""Ranked, live-validated locator candidates for one discovery-captured
click/input action (Phase 4).

Nothing here fabricates a candidate: every strategy's value comes from
either the real accessibility snapshot already captured for this action
(role + accessible name, and the live count of elements sharing that exact
pair — the same signal `mcp_discovery_agent._disambiguate_duplicate_names`
relies on) or a real DOM attribute read off the live page via
`MCPSession.evaluate` (id/data-testid/aria-label/placeholder/innerText).
Every non-role candidate is then live-validated with a second `evaluate`
call that counts how many elements the candidate's selector actually
matches on the real page right now — a locator that resolves to zero
elements is dropped rather than recommended, and one that resolves to more
than one is kept but demoted and flagged ambiguous.

Security: every JS string passed to `evaluate()` is one fixed,
developer-authored template; the only caller-controlled data ever embedded
into it goes through `json.dumps`, which produces a valid, fully-escaped JS
string/number literal for any Python value — never hand-built string
interpolation, and never page content or LLM output treated as code.
"""
from __future__ import annotations

import json
import logging
import re

from app.agents.automation.mcp_session import MCPSession, mask_snapshot_text
from app.agents.automation.snapshot_parser import parse_snapshot
from app.services.script_compiler import locator_policy
from app.services.script_compiler.naming import slugify

logger = logging.getLogger(__name__)

_RESULT_RE = re.compile(r"### Result\n(.*?)\n### Ran Playwright code", re.DOTALL)

# base confidence per strategy before live-validation adjustments
_BASE_SCORE = {"role": 90, "testid": 88, "label": 80, "placeholder": 70, "text": 55, "css": 35}
_AMBIGUOUS_CAP = 45
_UNVALIDATED_PENALTY = 20
_MAX_CANDIDATES = 5

_ELEMENT_ATTRS_JS = (
    "(element) => ({"
    "id: element.id || null,"
    "testidAttr: element.hasAttribute('data-testid') ? 'data-testid' : (element.hasAttribute('data-test') ? 'data-test' : null),"
    "testid: element.getAttribute('data-testid') || element.getAttribute('data-test') || null,"
    "ariaLabel: element.getAttribute('aria-label') || null,"
    "placeholder: element.getAttribute('placeholder') || null,"
    "text: (element.innerText || element.textContent || '').trim().slice(0, 120),"
    "tag: element.tagName.toLowerCase(),"
    "className: (typeof element.className === 'string' && element.className.trim())"
    " ? element.className.trim().split(/\\s+/).slice(0, 3).join('.') : null"
    "})"
)


def _parse_evaluate_result(raw: str):
    match = _RESULT_RE.search(raw)
    if not match:
        return None
    body = match.group(1).strip()
    if not body:
        return None
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        return None


def _text_match_count_js(value: str) -> str:
    return (
        "() => Array.from(document.querySelectorAll('body *'))"
        f".filter(el => el.children.length === 0 && (el.innerText || el.textContent || '').trim() === {json.dumps(value)})"
        ".length"
    )


def _css_count_js(selector: str) -> str:
    return f"() => document.querySelectorAll({json.dumps(selector)}).length"


async def _live_count(mcp_session: MCPSession, function_js: str) -> int | None:
    try:
        raw = await mcp_session.evaluate(function=function_js)
    except Exception:
        logger.warning("locator_ranking: evaluate() failed during live validation", exc_info=True)
        return None
    result = _parse_evaluate_result(raw)
    return result if isinstance(result, int) else None


def _score(base: int, count: int | None) -> tuple[int, bool, bool]:
    """Returns (confidence, unique, validated)."""
    if count is None:
        return max(base - _UNVALIDATED_PENALTY, 1), False, False
    if count == 1:
        return base, True, True
    if count == 0:
        return 0, False, True  # caller drops score==0 candidates
    return min(base, _AMBIGUOUS_CAP), False, True


async def rank_and_validate(
    mcp_session: MCPSession, *, raw_snapshot: str, target_ref: str | None,
    target_semantic: str | None, action_family: str,
) -> dict | None:
    if action_family not in ("click", "input") or not target_ref:
        return None

    parsed = parse_snapshot(raw_snapshot)
    element = next((el for el in parsed.elements if el.ref == target_ref), None)
    if element is None:
        return None

    role = element.role
    name = element.name

    candidates: list[dict] = []

    if name:
        same_pair_count = sum(1 for el in parsed.elements if el.role == role and el.name == name)
        confidence, unique, validated = _score(_BASE_SCORE["role"], same_pair_count)
        if confidence > 0:
            candidates.append({
                "strategy": "role", "value": mask_snapshot_text(name),
                "locator": locator_policy.render_locator_playwright("role", name, role),
                "confidence": confidence, "unique": unique, "validated": validated,
            })

    attrs: dict = {}
    try:
        raw_attrs = await mcp_session.evaluate(
            function=_ELEMENT_ATTRS_JS, element=target_semantic or target_ref, target=target_ref,
        )
        parsed_attrs = _parse_evaluate_result(raw_attrs)
        if isinstance(parsed_attrs, dict):
            attrs = parsed_attrs
    except Exception:
        logger.warning("locator_ranking: element-scoped evaluate() failed", exc_info=True)

    async def _add_candidate(strategy: str, raw_value: str | None, selector_for_count: str | None) -> None:
        if not raw_value or not str(raw_value).strip():
            return
        value = str(raw_value).strip()
        count = await _live_count(mcp_session, _css_count_js(selector_for_count)) if selector_for_count else None
        confidence, unique, validated = _score(_BASE_SCORE[strategy], count)
        if confidence <= 0:
            return
        candidates.append({
            "strategy": strategy, "value": mask_snapshot_text(value),
            "locator": locator_policy.render_locator_playwright(strategy, value),
            "confidence": confidence, "unique": unique, "validated": validated,
        })

    await _add_candidate("label", attrs.get("ariaLabel"), f"[aria-label={json.dumps(attrs.get('ariaLabel'))}]" if attrs.get("ariaLabel") else None)
    await _add_candidate("placeholder", attrs.get("placeholder"), f"[placeholder={json.dumps(attrs.get('placeholder'))}]" if attrs.get("placeholder") else None)
    testid_attr = attrs.get("testidAttr") or "data-testid"
    await _add_candidate("testid", attrs.get("testid"), f"[{testid_attr}={json.dumps(attrs.get('testid'))}]" if attrs.get("testid") else None)

    text_value = attrs.get("text")
    if text_value and len(text_value) <= 80:
        count = await _live_count(mcp_session, _text_match_count_js(text_value))
        confidence, unique, validated = _score(_BASE_SCORE["text"], count)
        if confidence > 0:
            candidates.append({
                "strategy": "text", "value": mask_snapshot_text(text_value),
                "locator": locator_policy.render_locator_playwright("text", text_value),
                "confidence": confidence, "unique": unique, "validated": validated,
            })

    css_selector = f"#{attrs['id']}" if attrs.get("id") else (
        f"{attrs['tag']}.{attrs['className']}" if attrs.get("tag") and attrs.get("className") else None
    )
    if css_selector:
        count = await _live_count(mcp_session, _css_count_js(css_selector))
        confidence, unique, validated = _score(_BASE_SCORE["css"], count)
        if confidence > 0:
            candidates.append({
                "strategy": "css", "value": css_selector,
                "locator": locator_policy.render_locator_playwright("css", css_selector),
                "confidence": confidence, "unique": unique, "validated": validated,
            })

    if not candidates:
        return None

    candidates.sort(key=lambda c: (locator_policy.rank(c["strategy"]), -c["confidence"]))
    candidates = candidates[:_MAX_CANDIDATES]

    return {
        "element_name": slugify(role, name or "unnamed"),
        "role": role,
        "page_url": parsed.page_url,
        "candidates": candidates,
    }
