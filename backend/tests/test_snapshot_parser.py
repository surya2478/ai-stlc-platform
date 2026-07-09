"""Snapshot parser tests, using the exact text shape captured from a live
@playwright/mcp 0.0.77 session during development (see mcp_discovery_agent.py
module docstring) — not a guessed/idealized format."""
from app.agents.automation.snapshot_parser import parse_snapshot

REAL_SNAPSHOT_TEXT = """### Page
- Page URL: http://127.0.0.1:8934/test_page.html
- Page Title: Test Login
- Console: 1 errors, 0 warnings
### Snapshot
```yaml
- generic [active] [ref=e1]:
  - heading "Sign in" [level=1] [ref=e2]
  - generic [ref=e3]:
    - text: Username
    - textbox "Username" [ref=e4]
    - text: Password
    - textbox "Password" [ref=e5]
    - button "Sign in" [ref=e6]
  - link "Other page" [ref=e7] [cursor=pointer]:
    - /url: /other
```
"""


def test_parses_page_metadata():
    parsed = parse_snapshot(REAL_SNAPSHOT_TEXT)
    assert parsed.page_url == "http://127.0.0.1:8934/test_page.html"
    assert parsed.page_title == "Test Login"


def test_parses_all_elements_with_correct_depth():
    parsed = parse_snapshot(REAL_SNAPSHOT_TEXT)
    roles_at_depth = [(el.depth, el.role, el.name) for el in parsed.elements]
    assert (0, "generic", None) in roles_at_depth
    assert (1, "heading", "Sign in") in roles_at_depth
    assert (2, "textbox", "Username") in roles_at_depth
    assert (2, "textbox", "Password") in roles_at_depth
    assert (2, "button", "Sign in") in roles_at_depth
    assert (1, "link", "Other page") in roles_at_depth


def test_link_href_attached_from_nested_url_line():
    parsed = parse_snapshot(REAL_SNAPSHOT_TEXT)
    link = next(el for el in parsed.elements if el.role == "link")
    assert link.href == "/other"


def test_refs_extracted_correctly():
    parsed = parse_snapshot(REAL_SNAPSHOT_TEXT)
    username = next(el for el in parsed.elements if el.name == "Username" and el.role == "textbox")
    assert username.ref == "e4"


def test_interactive_elements_filters_out_generic_and_text_and_heading():
    parsed = parse_snapshot(REAL_SNAPSHOT_TEXT)
    interactive_roles = {el.role for el in parsed.interactive_elements}
    assert interactive_roles == {"textbox", "button", "link"}
    assert len(parsed.interactive_elements) == 4


def test_attrs_parsed_as_key_value_and_bare_flags():
    parsed = parse_snapshot(REAL_SNAPSHOT_TEXT)
    root = next(el for el in parsed.elements if el.role == "generic" and el.depth == 0)
    assert root.attrs.get("active") == "true"
    heading = next(el for el in parsed.elements if el.role == "heading")
    assert heading.attrs.get("level") == "1"


def test_missing_yaml_fence_returns_empty_elements_but_keeps_page_metadata():
    text = "### Page\n- Page URL: http://x/\n- Page Title: X\n"
    parsed = parse_snapshot(text)
    assert parsed.page_url == "http://x/"
    assert parsed.elements == []


def test_empty_text_does_not_crash():
    parsed = parse_snapshot("")
    assert parsed.page_url is None
    assert parsed.page_title is None
    assert parsed.elements == []
