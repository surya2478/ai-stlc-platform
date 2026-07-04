"""Step parameter binding.

Manual test cases can include placeholders like `${field}` or `${field.nested}`
in step action and expected-result text. At run-start time, we substitute those
against a bound TestDataRecord and snapshot the resolved text onto the
ManualStepResult row so the tester sees real values (and the history is
immutable, even if the test data record changes later).

Syntax:
  ${customer_id}       — replaced with record["customer_id"]
  ${address.city}      — dotted path: record["address"]["city"]
  ${customer_id|N/A}   — fallback when the key is missing or null

Unresolved tokens are LEFT IN PLACE (not replaced with empty string) so the
tester can see exactly which bindings were missing.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Mapping

logger = logging.getLogger(__name__)

# Matches ${path} or ${path|fallback}. The path is one-or-more dot-separated
# identifiers. We deliberately don't allow nested ${} or arbitrary expressions —
# this is a substitution helper, not an eval engine.
_TOKEN_RE = re.compile(
    r"\$\{(?P<path>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)"
    r"(?:\|(?P<fallback>[^}]*))?\}"
)


def _walk(record: Mapping[str, Any] | None, path: str) -> Any | None:
    if not isinstance(record, Mapping):
        return None
    parts = path.split(".")
    current: Any = record
    for part in parts:
        if isinstance(current, Mapping) and part in current:
            current = current[part]
        else:
            return None
    return current


def substitute(text: str | None, record: Mapping[str, Any] | None) -> tuple[str | None, list[str]]:
    """Substitute ${path[|fallback]} tokens in `text` using `record`.

    Returns (resolved_text, missing_tokens).
    `missing_tokens` lists paths that had no value AND no fallback — useful for
    surfacing "you forgot to bind X" warnings in the UI.
    """
    if text is None:
        return None, []
    if not isinstance(text, str) or "${" not in text:
        return text, []

    missing: list[str] = []

    def replace(match: re.Match[str]) -> str:
        path = match.group("path")
        fallback = match.group("fallback")
        value = _walk(record, path)
        if value is None or value == "":
            if fallback is not None:
                return fallback
            missing.append(path)
            # Leave the original token in place so it's visible to the tester
            return match.group(0)
        # Dicts and lists get JSON-serialised so testers see clean output
        # ({"a": 1}) instead of Python repr ({'a': 1}). Primitives use str().
        if isinstance(value, (dict, list)):
            try:
                return json.dumps(value, ensure_ascii=False, default=str)
            except (TypeError, ValueError):
                return str(value)
        return str(value)

    return _TOKEN_RE.sub(replace, text), missing


def substitute_step(
    *,
    action: str | None,
    expected: str | None,
    record: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Apply substitution to a step's action + expected text in one shot."""
    resolved_action, missing_action = substitute(action, record)
    resolved_expected, missing_expected = substitute(expected, record)
    return {
        "action_text": resolved_action,
        "expected_text": resolved_expected,
        "missing_tokens": sorted(set(missing_action + missing_expected)),
    }
