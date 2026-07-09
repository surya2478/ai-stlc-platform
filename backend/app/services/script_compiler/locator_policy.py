"""
Locator policy (Phase 2.4).

Priority order (best -> worst): role > label > placeholder > text > testid
> css (exception) > xpath (explicit exception only). Shared by the Script
Compiler (renders the contract's declared strategy into a real Playwright
locator expression) and the Static Quality Gate (flags violations of the
policy in already-generated code).
"""
from __future__ import annotations

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


def render_locator_playwright(strategy: str, value: str, role_hint: str | None = None) -> str:
    """Render a Playwright TypeScript locator expression for a given
    strategy/value — the one place that decides what `getByX(...)` looks
    like, so the compiler's output is deterministic for a given contract."""
    if strategy == "role":
        role = role_hint or "button"
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


def render_locator_pytest(strategy: str, value: str, role_hint: str | None = None) -> str:
    """Render a Playwright-Python locator expression for the Pytest renderer
    (same semantics as `render_locator_playwright`, Python syntax)."""
    if strategy == "role":
        role = role_hint or "button"
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
