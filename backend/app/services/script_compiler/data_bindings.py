"""Test-data bindings are dotted paths, not flat names.

A contract declares `testDataBindings` by root name (`validOtherFields`) while
its steps dereference leaves of that root (`validOtherFields.firstName`). The
fixture renderers used to emit one flat `string` field per declared binding,
which produced a bundle that compiled and then died on its first action:

    export interface TestDataFixture { validOtherFields: string; }
    ...
    await page.fill(TEST_DATA.validOtherFields.firstName);
    // Error: locator.fill: value: expected string, got undefined

`''.firstName` is `undefined`, and TypeScript never objected because Playwright
transpiles specs with esbuild, which strips types without checking them.

So the shape the fixture declares has to be derived from the paths the bundle
actually dereferences. A node with children is an object; a node without them is
a string leaf sourced from one environment variable.
"""
from __future__ import annotations

import re

from app.agents.automation.generation_contract import AutomationGenerationContract

# A bare TS/JS identifier, safe to emit unquoted as an object key.
_IDENTIFIER = re.compile(r"^[A-Za-z_$][A-Za-z0-9_$]*$")

# Nested tree: {"validOtherFields": {"firstName": {}, "lastName": {}}}.
# An empty dict marks a leaf.
BindingTree = dict[str, "BindingTree"]


def binding_paths(contract: AutomationGenerationContract) -> list[str]:
    """Every distinct dotted path the compiled bundle will dereference.

    Declared binding names are included alongside the paths the steps use, so a
    binding declared but never referenced still reaches the fixture (and a path
    referenced but never declared still renders rather than crashing).
    """
    paths = {b.name for b in contract.test_data_bindings if b.name}
    paths.update(step.data_binding for step in contract.steps if step.data_binding)
    return sorted(paths)


def binding_tree(contract: AutomationGenerationContract) -> BindingTree:
    """Nest `binding_paths` by their dots.

    A path that is both a leaf and a parent (`a` and `a.b` both referenced)
    resolves to the parent — an object is the only shape that can serve `a.b`.
    `validate_bindings` reports the conflict separately; rendering cannot.
    """
    tree: BindingTree = {}
    for path in binding_paths(contract):
        node = tree
        for part in path.split("."):
            part = part.strip()
            if not part:
                continue
            node = node.setdefault(part, {})
    return tree


def is_leaf(node: BindingTree) -> bool:
    return not node


def leaf_paths(tree: BindingTree, prefix: str = "") -> list[str]:
    """The paths that render as string fields and that steps actually read.

    A declared root like `validOtherFields` is not a leaf once any step reads
    `validOtherFields.firstName` — it renders as an object, so validating it as
    a value would report a failure that does not exist.
    """
    paths: list[str] = []
    for name, child in tree.items():
        path = f"{prefix}.{name}" if prefix else name
        if is_leaf(child):
            paths.append(path)
        else:
            paths.extend(leaf_paths(child, path))
    return paths


def key_literal(name: str) -> str:
    """Object key, quoted only when it is not a bare identifier."""
    if _IDENTIFIER.match(name):
        return name
    escaped = name.replace("\\", "\\\\").replace("'", "\\'")
    return f"'{escaped}'"


def resolve_path(data: object, path: str) -> tuple[bool, object]:
    """Walk a dotted path through parsed test data.

    Returns (found, value). Used by the generation-time validator to tell a
    binding that resolves from one that will silently be `undefined`.
    """
    current = data
    for part in path.split("."):
        part = part.strip()
        if not part:
            continue
        if not isinstance(current, dict) or part not in current:
            return False, None
        current = current[part]
    return True, current
