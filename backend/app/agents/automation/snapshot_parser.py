"""
Deterministic parser for @playwright/mcp's `browser_navigate`/`browser_snapshot`
text output (Phase 3.3/3.5).

Verified against the server's real output (captured via a live smoke test
against @playwright/mcp 0.0.77), which looks like:

    ### Page
    - Page URL: http://example.com/login
    - Page Title: Sign in
    ### Snapshot
    ```yaml
    - generic [active] [ref=e1]:
      - heading "Sign in" [level=1] [ref=e2]
      - generic [ref=e3]:
        - text: Username
        - textbox "Username" [ref=e4]
        - button "Sign in" [ref=e6]
      - link "Other page" [ref=e7] [cursor=pointer]:
        - /url: /other
    ```

This is a mechanical extraction only — it never interprets *meaning*, only
structure (role, accessible name, ref, nesting, href). Business-meaning
mapping is the discovery agent's job, one level up, and only ever runs
against the parsed *structure*, not raw text handed to an LLM as instructions.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

_PAGE_URL_RE = re.compile(r"^-\s*Page URL:\s*(.+)$", re.MULTILINE)
_PAGE_TITLE_RE = re.compile(r"^-\s*Page Title:\s*(.+)$", re.MULTILINE)
_YAML_FENCE_RE = re.compile(r"```ya?ml\s*\n(.*?)```", re.DOTALL)

_LINE_RE = re.compile(r"^(?P<indent>\s*)-\s+(?P<rest>.*)$")
_TEXT_LEAF_RE = re.compile(r"^text:\s*(?P<content>.*)$")
_URL_LEAF_RE = re.compile(r"^/url:\s*(?P<url>.*)$")
_ROLE_NAME_RE = re.compile(r'^(?P<role>[A-Za-z_][\w-]*)\s+"(?P<name>[^"]*)"\s*(?P<attrs>.*?):?\s*$')
_ROLE_ONLY_RE = re.compile(r"^(?P<role>[A-Za-z_][\w-]*)\s*(?P<attrs>.*?):?\s*$")
_ATTR_RE = re.compile(r"\[([^\]]*)\]")

# Roles worth recommending a locator for — structural/decorative roles
# (generic, none, ...) are parsed but filtered out by callers that only
# want actionable elements.
INTERACTIVE_ROLES = frozenset({
    "textbox", "button", "link", "checkbox", "radio", "combobox", "listbox",
    "option", "menuitem", "tab", "switch", "slider", "searchbox", "spinbutton",
})


@dataclass
class SnapshotElement:
    role: str
    name: str | None
    ref: str | None
    depth: int
    attrs: dict[str, str] = field(default_factory=dict)
    href: str | None = None

    @property
    def is_interactive(self) -> bool:
        return self.role in INTERACTIVE_ROLES


@dataclass
class ParsedSnapshot:
    page_url: str | None
    page_title: str | None
    elements: list[SnapshotElement] = field(default_factory=list)

    @property
    def interactive_elements(self) -> list[SnapshotElement]:
        return [el for el in self.elements if el.is_interactive]


def _parse_attrs(attrs_text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for raw in _ATTR_RE.findall(attrs_text):
        if "=" in raw:
            key, _, value = raw.partition("=")
            attrs[key.strip()] = value.strip()
        else:
            attrs[raw.strip()] = "true"
    return attrs


def _parse_element_line(rest: str, depth: int) -> SnapshotElement | None:
    match = _ROLE_NAME_RE.match(rest)
    if match:
        attrs = _parse_attrs(match.group("attrs"))
        return SnapshotElement(
            role=match.group("role"), name=match.group("name"), ref=attrs.get("ref"),
            depth=depth, attrs=attrs,
        )
    match = _ROLE_ONLY_RE.match(rest)
    if match:
        attrs = _parse_attrs(match.group("attrs"))
        return SnapshotElement(
            role=match.group("role"), name=None, ref=attrs.get("ref"), depth=depth, attrs=attrs,
        )
    return None


def parse_snapshot(raw: str) -> ParsedSnapshot:
    """Parse the full text block returned by browser_navigate/browser_snapshot
    into page metadata + a flat list of structural elements with depth."""
    page_url_match = _PAGE_URL_RE.search(raw)
    page_title_match = _PAGE_TITLE_RE.search(raw)
    page_url = page_url_match.group(1).strip() if page_url_match else None
    page_title = page_title_match.group(1).strip() if page_title_match else None

    yaml_match = _YAML_FENCE_RE.search(raw)
    if not yaml_match:
        return ParsedSnapshot(page_url=page_url, page_title=page_title, elements=[])

    elements: list[SnapshotElement] = []
    by_depth: dict[int, SnapshotElement] = {}

    for line in yaml_match.group(1).splitlines():
        if not line.strip():
            continue
        line_match = _LINE_RE.match(line)
        if not line_match:
            continue
        indent = line_match.group("indent")
        rest = line_match.group("rest").strip()
        depth = len(indent) // 2

        url_match = _URL_LEAF_RE.match(rest)
        if url_match:
            parent = by_depth.get(depth - 1)
            if parent is not None:
                parent.href = url_match.group("url").strip()
            continue

        text_match = _TEXT_LEAF_RE.match(rest)
        if text_match:
            el = SnapshotElement(role="text", name=text_match.group("content").strip(), ref=None, depth=depth)
            elements.append(el)
            by_depth[depth] = el
            continue

        el = _parse_element_line(rest, depth)
        if el is not None:
            elements.append(el)
            by_depth[depth] = el

    return ParsedSnapshot(page_url=page_url, page_title=page_title, elements=elements)
