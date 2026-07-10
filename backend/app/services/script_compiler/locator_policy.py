"""
Locator policy (Phase 2.4).

Priority order (best -> worst): role > label > placeholder > text > testid
> css (exception) > xpath (explicit exception only). Shared by the Script
Compiler (renders the contract's declared strategy into a real Playwright
locator expression) and the Static Quality Gate (flags violations of the
policy in already-generated code).
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from app.agents.automation.generation_contract import AutomationGenerationContract

LOCATOR_PRIORITY: tuple[str, ...] = ("role", "label", "placeholder", "text", "testid", "css", "xpath")

_RANK = {strategy: i for i, strategy in enumerate(LOCATOR_PRIORITY)}

# These strategies are still renderable — an agent may have no better
# option — but the static gate flags them unless recorded as an accepted
# exception, since they're the ones known to break under layout/DOM churn.
EXCEPTION_REQUIRED_STRATEGIES = frozenset({"css", "xpath"})


def rank(strategy: str) -> int:
    """Lower is better. Unknown strategies sort last (worst)."""
    return _RANK.get(strategy, len(LOCATOR_PRIORITY))


def requires_exception(strategy: str) -> bool:
    return strategy in EXCEPTION_REQUIRED_STRATEGIES


def is_preferred_over(a: str, b: str) -> bool:
    """True if strategy `a` is preferred (higher priority) over `b`."""
    return rank(a) < rank(b)


def _escape_js(value: str) -> str:
    """Escape a value for embedding inside a single-quoted JS/TS string
    literal — mirrors naming.js_string_literal's escaping without the
    quote-wrapping, since callers here build their own surrounding syntax."""
    return value.replace("\\", "\\\\").replace("'", "\\'")


def _escape_py(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def render_locator_playwright(strategy: str, value: str, role_hint: str | None = None) -> str:
    """Render a Playwright TypeScript locator expression for a given
    strategy/value — the one place that decides what `getByX(...)` looks
    like, so the compiler's output is deterministic for a given contract.

    Every interpolated value is escaped — a live run produced
    `page.locator('input[name='q']')` (a CSS selector's own single quote,
    from `[name='q']` attribute-selector syntax, terminated the string
    literal early) before this was fixed. CSS/xpath selectors routinely
    contain quotes; role names/labels/text can too.
    """
    value = _escape_js(value)
    if strategy == "role":
        role = _escape_js(role_hint or "button")
        return f"page.getByRole('{role}', {{ name: '{value}' }})"
    if strategy == "label":
        return f"page.getByLabel('{value}')"
    if strategy == "placeholder":
        return f"page.getByPlaceholder('{value}')"
    if strategy == "text":
        return f"page.getByText('{value}')"
    if strategy == "testid":
        return f"page.getByTestId('{value}')"
    if strategy == "css":
        return f"page.locator('{value}')"
    if strategy == "xpath":
        return f"page.locator('xpath={value}')"
    raise ValueError(f"Unknown locator strategy: {strategy}")


_QUOTED = r"((?:[^'\\]|\\.)*)"  # a single-quoted JS string body, escapes tolerated

_PARSE_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("role", re.compile(rf"^page\.getByRole\('{_QUOTED}',\s*\{{\s*name:\s*'{_QUOTED}'\s*\}}\)$")),
    ("role_no_name", re.compile(rf"^page\.getByRole\('{_QUOTED}'\)$")),
    ("label", re.compile(rf"^page\.getByLabel\('{_QUOTED}'\)$")),
    ("placeholder", re.compile(rf"^page\.getByPlaceholder\('{_QUOTED}'\)$")),
    ("text", re.compile(rf"^page\.getByText\('{_QUOTED}'\)$")),
    ("testid", re.compile(rf"^page\.getByTestId\('{_QUOTED}'\)$")),
    ("xpath", re.compile(rf"^page\.locator\('xpath={_QUOTED}'\)$")),
    ("css", re.compile(rf"^page\.locator\('{_QUOTED}'\)$")),
)


def _unescape_js(value: str) -> str:
    """Inverse of _escape_js — turn `\\'` back into `'` and `\\\\` back into
    `\\`. Order matters: undo the quote-escape first, char by char, so a
    literal `\\\\'` (an escaped backslash immediately followed by an
    unrelated escaped quote) doesn't get misread as `\\` + unescaped `'`."""
    result = []
    i = 0
    while i < len(value):
        if value[i] == "\\" and i + 1 < len(value) and value[i + 1] in ("\\", "'"):
            result.append(value[i + 1])
            i += 2
        else:
            result.append(value[i])
            i += 1
    return "".join(result)


def parse_locator_playwright(rendered: str) -> tuple[str, str, str | None] | None:
    """Inverse of `render_locator_playwright` — recover (strategy, value,
    role_hint) from an already-rendered locator expression.

    Used to ground a contract element directly from a locator_map catalog
    entry's `recommended_locator` string when the LLM names an element after
    a discovered one but mis-transcribes its strategy/value/roleHint fields
    (confirmed via a live run: the LLM swapped an element's ARIA role and
    accessible name between `roleHint`/`locatorValue`, producing a locator
    that resolved nothing on the real page). Returns None if the string
    doesn't match any known render pattern — callers must treat that as
    "can't ground this one", not fail outright.

    Extracted groups are unescaped back to their original form — without
    this, a value containing a quote would come back from parsing still
    escaped (e.g. `input[name=\\'q\\']`), which then gets *re*-escaped on
    the next render, corrupting the locator further with each round-trip.
    """
    for kind, pattern in _PARSE_PATTERNS:
        m = pattern.match(rendered.strip())
        if not m:
            continue
        if kind == "role":
            return "role", _unescape_js(m.group(2)), _unescape_js(m.group(1))
        if kind == "role_no_name":
            return "role", "", _unescape_js(m.group(1))
        if kind in ("label", "placeholder", "text", "testid", "xpath", "css"):
            return kind, _unescape_js(m.group(1)), None
    return None


def render_locator_pytest(strategy: str, value: str, role_hint: str | None = None) -> str:
    """Render a Playwright-Python locator expression for the Pytest renderer
    (same semantics as `render_locator_playwright`, Python syntax)."""
    value = _escape_py(value)
    if strategy == "role":
        role = _escape_py(role_hint or "button")
        return f"page.get_by_role('{role}', name='{value}')"
    if strategy == "label":
        return f"page.get_by_label('{value}')"
    if strategy == "placeholder":
        return f"page.get_by_placeholder('{value}')"
    if strategy == "text":
        return f"page.get_by_text('{value}')"
    if strategy == "testid":
        return f"page.get_by_test_id('{value}')"
    if strategy == "css":
        return f"page.locator('{value}')"
    if strategy == "xpath":
        return f"page.locator('xpath={value}')"
    raise ValueError(f"Unknown locator strategy: {strategy}")


def filter_catalog_by_page(catalog: list[dict] | None, base_url: str | None) -> list[dict] | None:
    """Scope a locator_map catalog down to entries whose discovered page
    shares the same host as the test's own entry-point URL.

    A locator_map catalog for one "application" can span several distinct
    pages discovered across a multi-page flow (e.g. a site and the OAuth
    provider it redirects through). Without this, both the LLM prompt
    (GROUNDED_LOCATORS_INSTRUCTION) and `ground_page_object_elements` could
    match an element by name against a locator captured on an entirely
    different page than the one this specific test ever navigates to —
    confirmed via a live run where a Google-search test's "search box" got
    grounded against an accounts.google.com sign-in field from the same
    application's catalog, which doesn't exist on the page the test
    actually visits. Falls back to the full catalog when nothing matches
    the host, or when base_url can't be parsed, rather than silently
    discarding every entry.
    """
    if not catalog or not base_url:
        return catalog
    base_host = urlparse(base_url).netloc.lower()
    if not base_host:
        return catalog
    scoped = [entry for entry in catalog if urlparse(entry.get("page") or "").netloc.lower() == base_host]
    return scoped or catalog


def ground_page_object_elements(contract: "AutomationGenerationContract", catalog: list[dict] | None) -> None:
    """Force-correct an element's locator fields from a locator_map catalog
    when a contract names it after a discovered element (matched by
    element_name), mutating the contract's page objects in place.

    Both `automation_agent` (first generation) and `repair_agent` (locator
    patches) ask the LLM to reuse a catalog element's exact strategy/value/
    roleHint (see automation_agent.GROUNDED_LOCATORS_INSTRUCTION), but
    transcribing three separate fields out of a rendered locator string is
    itself error-prone — confirmed via a live run where the LLM swapped an
    element's ARIA role and accessible name between roleHint/locatorValue,
    producing a locator that matched nothing on the real page despite naming
    the right element. Overriding directly from the catalog's
    `recommended_locator` (via `parse_locator_playwright`) removes that
    failure mode entirely for any element the LLM correctly identified by
    name, rather than just detecting the mistake after the fact.
    """
    if not catalog:
        return
    catalog_by_name = {entry["element_name"]: entry for entry in catalog if entry.get("element_name")}
    for page_object in contract.page_objects:
        for element in page_object.elements:
            entry = catalog_by_name.get(element.name)
            if entry is None:
                continue
            parsed = parse_locator_playwright(entry.get("recommended_locator") or "")
            if parsed is None:
                continue
            strategy, value, role_hint = parsed
            element.locator_strategy = strategy
            element.locator_value = value
            element.role_hint = role_hint
