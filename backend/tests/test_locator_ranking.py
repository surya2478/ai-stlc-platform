"""Ranked, live-validated locator candidates (Phase 4).

`_FakeMCP.evaluate()` replays queued canned responses shaped exactly like
the real `@playwright/mcp` server's output — captured live via
`docker compose exec worker python …` against a real browser session before
writing this module (see the implementation plan): `browser_evaluate`
always returns `"### Result\\n<json>\\n### Ran Playwright code\\n..."`.
"""
from app.services.discovery import locator_ranking

SNAPSHOT_UNIQUE = """### Page
- Page URL: https://example.com/checkout
- Page Title: Checkout
### Snapshot
```yaml
- generic [ref=e1]:
  - button "Save" [ref=e2]
  - textbox "Promo code" [ref=e4]
```
"""

SNAPSHOT_AMBIGUOUS = """### Page
- Page URL: https://example.com/checkout
- Page Title: Checkout
### Snapshot
```yaml
- generic [ref=e1]:
  - button "Submit" [ref=e2]
  - button "Submit" [ref=e3]
```
"""


class _FakeMCP:
    """Minimal stand-in for MCPSession.evaluate() — replays queued
    responses (or raises, for an entry that is an Exception instance)."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls: list[tuple] = []

    async def evaluate(self, *, function, element=None, target=None):
        self.calls.append((function, element, target))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def _result(value_json: str) -> str:
    return f"### Result\n{value_json}\n### Ran Playwright code\n```js\nawait page.evaluate(...);\n```"


NULL_ATTRS = _result(
    '{"id": null, "testidAttr": null, "testid": null, "ariaLabel": null, '
    '"placeholder": null, "text": "", "tag": "button", "className": null}'
)


async def _run(*args, **kwargs):
    return await locator_ranking.rank_and_validate(*args, **kwargs)


# ── _parse_evaluate_result — exact live-captured shapes ──────────────────

def test_parse_evaluate_result_int():
    raw = '### Result\n1\n### Ran Playwright code\n```js\nawait page.evaluate(\'...\');\n```'
    assert locator_ranking._parse_evaluate_result(raw) == 1


def test_parse_evaluate_result_string():
    raw = '### Result\n"Example Domain"\n### Ran Playwright code\n```js\n...\n```'
    assert locator_ranking._parse_evaluate_result(raw) == "Example Domain"


def test_parse_evaluate_result_object():
    raw = '### Result\n{\n  "tag": "A",\n  "href": "https://iana.org/domains/example"\n}\n### Ran Playwright code\n```js\n...\n```'
    assert locator_ranking._parse_evaluate_result(raw) == {"tag": "A", "href": "https://iana.org/domains/example"}


def test_parse_evaluate_result_no_marker_returns_none():
    assert locator_ranking._parse_evaluate_result("no marker here") is None


# ── rank_and_validate ──────────────────────────────────────────────────

def test_returns_none_for_non_click_input_family():
    import anyio

    async def _go():
        mcp = _FakeMCP([])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e2", target_semantic="Save", action_family="read",
        )

    assert anyio.run(_go) is None


def test_returns_none_when_ref_not_found():
    import anyio

    async def _go():
        mcp = _FakeMCP([NULL_ATTRS])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e999", target_semantic="Save", action_family="click",
        )

    assert anyio.run(_go) is None


def test_ambiguous_role_capped_and_flagged_not_unique():
    import anyio

    async def _go():
        mcp = _FakeMCP([NULL_ATTRS])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_AMBIGUOUS, target_ref="e2", target_semantic="Submit", action_family="click",
        )

    result = anyio.run(_go)
    assert result is not None
    role_candidate = next(c for c in result["candidates"] if c["strategy"] == "role")
    assert role_candidate["unique"] is False
    assert role_candidate["confidence"] <= locator_ranking._AMBIGUOUS_CAP


def test_unique_role_scores_full_base_confidence():
    import anyio

    async def _go():
        mcp = _FakeMCP([NULL_ATTRS])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e2", target_semantic="Save", action_family="click",
        )

    result = anyio.run(_go)
    role_candidate = next(c for c in result["candidates"] if c["strategy"] == "role")
    assert role_candidate["unique"] is True
    assert role_candidate["confidence"] == locator_ranking._BASE_SCORE["role"]
    assert result["element_name"] == "button_save"
    assert result["page_url"] == "https://example.com/checkout"


def test_candidate_dropped_when_selector_resolves_to_zero():
    import anyio

    attrs = _result(
        '{"id": null, "testidAttr": "data-testid", "testid": "save-btn", "ariaLabel": null, '
        '"placeholder": null, "text": "", "tag": "button", "className": null}'
    )
    zero_count = _result("0")

    async def _go():
        mcp = _FakeMCP([attrs, zero_count])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e2", target_semantic="Save", action_family="click",
        )

    result = anyio.run(_go)
    assert all(c["strategy"] != "testid" for c in result["candidates"])


def test_unique_testid_and_text_candidates_kept_and_ordered_by_policy():
    import anyio

    attrs = _result(
        '{"id": null, "testidAttr": "data-testid", "testid": "save-btn", "ariaLabel": null, '
        '"placeholder": null, "text": "Save", "tag": "button", "className": null}'
    )
    one_count = _result("1")

    async def _go():
        mcp = _FakeMCP([attrs, one_count, one_count])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e2", target_semantic="Save", action_family="click",
        )

    result = anyio.run(_go)
    strategies = [c["strategy"] for c in result["candidates"]]
    # Policy priority: role > label > placeholder > text > testid > css.
    assert strategies == ["role", "text", "testid"]
    assert all(c["unique"] for c in result["candidates"])


def test_element_scoped_evaluate_failure_is_non_fatal():
    import anyio

    async def _go():
        mcp = _FakeMCP([RuntimeError("MCP tool 'browser_evaluate' returned an error")])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e2", target_semantic="Save", action_family="click",
        )

    result = anyio.run(_go)
    # Only the role candidate survives — everything else needed the failed
    # element-attrs call.
    assert [c["strategy"] for c in result["candidates"]] == ["role"]


def test_count_validation_failure_demotes_candidate_instead_of_dropping():
    import anyio

    attrs = _result(
        '{"id": null, "testidAttr": "data-testid", "testid": "save-btn", "ariaLabel": null, '
        '"placeholder": null, "text": "", "tag": "button", "className": null}'
    )

    async def _go():
        mcp = _FakeMCP([attrs, RuntimeError("evaluate failed")])
        return await locator_ranking.rank_and_validate(
            mcp, raw_snapshot=SNAPSHOT_UNIQUE, target_ref="e2", target_semantic="Save", action_family="click",
        )

    result = anyio.run(_go)
    testid_candidate = next(c for c in result["candidates"] if c["strategy"] == "testid")
    assert testid_candidate["validated"] is False
    assert testid_candidate["confidence"] == locator_ranking._BASE_SCORE["testid"] - locator_ranking._UNVALIDATED_PENALTY


def test_adversarial_value_is_json_escaped_not_string_interpolated():
    js = locator_ranking._css_count_js('foo"bar\\baz')
    # A hand-built f-string like f"...{value}..." would break the JS source
    # here; json.dumps must have produced a fully escaped literal instead.
    assert '\\"' in js or "foo" in js
    import json

    # The selector round-trips through json.loads back to the exact value —
    # proof it was embedded as a proper JS string literal, not concatenated.
    start = js.index("querySelectorAll(") + len("querySelectorAll(")
    end = js.index(").length")
    assert json.loads(js[start:end]) == 'foo"bar\\baz'
