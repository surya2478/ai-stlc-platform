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


# A locator value that starts like this is an already-rendered expression that
# leaked into a contract field, never a real accessible name, label or selector.
_RENDERED_LOCATOR_PREFIX = re.compile(r"^\s*page\.(getBy[A-Za-z]+|locator)\(")


def render_locator_playwright(
    strategy: str, value: str, role_hint: str | None = None, nth: int | None = None
) -> str:
    """Render a Playwright TypeScript locator expression for a given
    strategy/value — the one place that decides what `getByX(...)` looks
    like, so the compiler's output is deterministic for a given contract.

    Every interpolated value is escaped — a live run produced
    `page.locator('input[name='q']')` (a CSS selector's own single quote,
    from `[name='q']` attribute-selector syntax, terminated the string
    literal early) before this was fixed. CSS/xpath selectors routinely
    contain quotes; role names/labels/text can too.

    `nth`, when given, appends `.nth(N)` — the positional disambiguator for
    when the same (role, accessible name) pair genuinely resolves to
    multiple real elements on one page (e.g. two identically-labelled
    "Show password" icon buttons). Without it, the base locator alone
    causes a Playwright "strict mode violation" at runtime (confirmed via a
    live run) since it isn't unique on the real page.

    A value that is *itself* an already-rendered locator is recovered rather
    than embedded. Confirmed across 8 live failures: the LLM put a whole
    expression into `locatorValue`, and this function dutifully escaped it
    into an accessible name, producing

        getByRole('link', { name: 'page.getByRole(\\'link\\', ...)' })

    which cannot match any real element and fails 15 seconds later with a
    message that blames the page rather than the contract. `ground_page_object_elements`
    only repairs elements the LLM named after a catalog entry, so anything it
    renamed reached here uncorrected. Parsing it back is exact — the inverse
    of this very function — and turns a guaranteed runtime failure into the
    locator that was meant.
    """
    if value and _RENDERED_LOCATOR_PREFIX.match(value):
        recovered = parse_locator_playwright(value)
        if recovered is None:
            # Unparseable, and it cannot be a real accessible name either. Fail
            # at compile time, where the static gate reports it against the
            # contract, instead of emitting a script that is certain to time out.
            raise ValueError(
                "locator_value is a rendered locator expression that could not be "
                f"parsed back: {value!r}. The contract element must carry a plain "
                "strategy/value/roleHint, not a compiled locator string."
            )
        strategy, value, recovered_role_hint, recovered_nth = recovered
        role_hint = recovered_role_hint or role_hint
        nth = recovered_nth if nth is None else nth

    value = _escape_js(value)
    if strategy == "role":
        role = _escape_js(role_hint or "button")
        base = f"page.getByRole('{role}', {{ name: '{value}', exact: true }})"
    elif strategy == "label":
        base = f"page.getByLabel('{value}')"
    elif strategy == "placeholder":
        base = f"page.getByPlaceholder('{value}')"
    elif strategy == "text":
        base = f"page.getByText('{value}')"
    elif strategy == "testid":
        base = f"page.getByTestId('{value}')"
    elif strategy == "css":
        base = f"page.locator('{value}')"
    elif strategy == "xpath":
        base = f"page.locator('xpath={value}')"
    else:
        raise ValueError(f"Unknown locator strategy: {strategy}")
    return f"{base}.nth({nth})" if nth is not None else base


_QUOTED = r"((?:[^'\\]|\\.)*)"  # a single-quoted JS string body, escapes tolerated
_NTH_SUFFIX = re.compile(r"^(.*)\.nth\((\d+)\)$")

_PARSE_PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("role", re.compile(rf"^page\.getByRole\('{_QUOTED}',\s*\{{\s*name:\s*'{_QUOTED}'(?:,\s*exact:\s*(true|false))?\s*\}}\)$")),
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


def parse_locator_playwright(rendered: str) -> tuple[str, str, str | None, int | None] | None:
    """Inverse of `render_locator_playwright` — recover (strategy, value,
    role_hint, nth) from an already-rendered locator expression.

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

    A trailing `.nth(N)` (see render_locator_playwright) is stripped first
    and returned separately — the base-locator patterns below never need to
    know about it.
    """
    candidate = rendered.strip()
    nth: int | None = None
    nth_match = _NTH_SUFFIX.match(candidate)
    if nth_match:
        candidate = nth_match.group(1)
        nth = int(nth_match.group(2))
    for kind, pattern in _PARSE_PATTERNS:
        m = pattern.match(candidate)
        if not m:
            continue
        if kind == "role":
            return "role", _unescape_js(m.group(2)), _unescape_js(m.group(1)), nth
        if kind == "role_no_name":
            return "role", "", _unescape_js(m.group(1)), nth
        if kind in ("label", "placeholder", "text", "testid", "xpath", "css"):
            return kind, _unescape_js(m.group(1)), None, nth
    return None


def render_locator_pytest(strategy: str, value: str, role_hint: str | None = None) -> str:
    """Render a Playwright-Python locator expression for the Pytest renderer
    (same semantics as `render_locator_playwright`, Python syntax)."""
    value = _escape_py(value)
    if strategy == "role":
        role = _escape_py(role_hint or "button")
        return f"page.get_by_role('{role}', name='{value}', exact=True)"
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


def _explored_paths(explored_page_paths: list[str] | None) -> list[str]:
    paths = []
    for url in explored_page_paths or []:
        parsed = urlparse(url)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        paths.append(path)
    return paths


def check_url_targets_grounded(
    contract: "AutomationGenerationContract", explored_page_paths: list[str] | None
) -> list[str]:
    """The navigation counterpart of element grounding: verify every
    wait_for_url step and url-type assertion targets a page the planner
    actually captured, not an LLM-guessed pattern.

    A multi-hop flow (click a link, land on a second page) needs its
    destination checked against the FULL set of explored pages, not just
    the test's own entry page — that's what explored_page_paths carries
    (every page the planner's crawl visited for this application). Returns
    descriptive refs for anything that doesn't match any explored path, in
    the same shape as _check_grounding's ungrounded_elements — callers feed
    both into the same retry/warning machinery.

    Substring matching, not exact equality: a wait_for_url regex like
    "role=candidate" is correctly grounded against the explored path
    "/sign-up?role=candidate" without needing to reproduce it verbatim.
    Only regex anchors (^ $) are stripped from the needle — NOT a leading
    "/", which is semantically load-bearing (a bug caught by the very live
    failure this function exists to catch: "/candidate" must NOT match
    "/sign-up?role=candidate" just because "candidate" appears after "=" —
    stripping the slash first would erase exactly the distinction that made
    the real regex fail against the real URL). Skipped entirely when no
    explored paths are known (regular, non-Studio test cases) — silence,
    not a false positive, when there's nothing to check against.
    """
    paths = _explored_paths(explored_page_paths)
    if not paths:
        return []

    def _grounded(value: str | None) -> bool:
        if not value:
            return True
        needle = value.strip().strip("^$")
        if not needle:
            return True
        return any(needle.lower() in path.lower() for path in paths)

    ungrounded: list[str] = []
    for step in contract.steps:
        if step.action == "wait_for_url" and not _grounded(step.value):
            ungrounded.append(f"wait_for_url:{step.value}")
    for assertion in contract.assertions:
        if assertion.type == "url" and not _grounded(assertion.expected):
            ungrounded.append(f"url_assertion:{assertion.expected}")
    return ungrounded


_FILLABLE_ROLE_HINTS = frozenset({"textbox", "combobox", "searchbox", "search"})


def _apply_catalog_entry(element, entry: dict) -> bool:
    parsed = parse_locator_playwright(entry.get("recommended_locator") or "")
    if parsed is None:
        return False
    strategy, value, role_hint, nth = parsed
    element.locator_strategy = strategy
    element.locator_value = value
    element.role_hint = role_hint
    element.nth = nth
    return True


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

    Also covers a second, harder failure mode confirmed via three
    consecutive live regenerations of the same test case: the LLM never
    reused the catalog's element name OR locator at all — inventing
    "searchBar"/input[name='q'], then an unnamed searchBox, then
    "searchInput"/getByPlaceholder('Search'), none matching the catalog's
    "combobox" by name, so nothing above ever triggers. When a "fill" step
    targets an element that's still ungrounded after name-matching, and the
    catalog has exactly one unambiguous text-input-like element (role
    textbox/combobox/searchbox) on this page, ground that step's element to
    it regardless of what the LLM called it or what locator it guessed —
    deliberately narrow to the single-candidate case so it can never
    silently pick the wrong field among several inputs.
    """
    if not catalog:
        return
    catalog_by_name = {entry["element_name"]: entry for entry in catalog if entry.get("element_name")}
    matched_by_name: set[str] = set()
    for page_object in contract.page_objects:
        for element in page_object.elements:
            entry = catalog_by_name.get(element.name)
            if entry is None:
                continue
            if _apply_catalog_entry(element, entry):
                matched_by_name.add(element.name)

    text_input_candidates = []
    for entry in catalog:
        parsed = parse_locator_playwright(entry.get("recommended_locator") or "")
        if parsed and parsed[0] == "role" and (parsed[2] or "").lower() in _FILLABLE_ROLE_HINTS:
            text_input_candidates.append(entry)
    if len(text_input_candidates) != 1:
        return
    fallback_entry = text_input_candidates[0]

    elements_by_ref = {
        f"{page_object.name}.{element.name}": element
        for page_object in contract.page_objects
        for element in page_object.elements
    }
    for step in contract.steps:
        if step.action != "fill" or not step.target:
            continue
        element = elements_by_ref.get(step.target)
        if element is None or element.name in matched_by_name:
            continue
        _apply_catalog_entry(element, fallback_entry)
