"""Wave 3 / AUT-012: the snapshot manifest identifies bytes, not just pointers.

`build_snapshot_payload` froze `script_id` and `script_version` — which
executable was chosen, never what it contained. The legacy PATCH route can still
rewrite an approved row's `compiled_files` in place without opening a new
version (AUT-003), so those two references could point at different bytes than
they did at publication and the snapshot checksum would not move.
"""
from __future__ import annotations

from types import SimpleNamespace

from app.services.automation_suite.lifecycle import compiled_bundle_digest


def _script(files):
    return SimpleNamespace(id=1, version=1, framework="playwright", compiled_files=files)


def test_digest_is_stable_for_identical_bundles():
    a = _script({"specs/x.spec.ts": "await page.goto('/');"})
    b = _script({"specs/x.spec.ts": "await page.goto('/');"})
    assert compiled_bundle_digest(a) == compiled_bundle_digest(b)


def test_digest_is_independent_of_key_order():
    """Otherwise a bundle that merely serialized differently would read as drift
    and block a perfectly valid run."""
    a = _script({"a.ts": "1", "b.ts": "2"})
    b = _script({"b.ts": "2", "a.ts": "1"})
    assert compiled_bundle_digest(a) == compiled_bundle_digest(b)


def test_digest_changes_when_content_changes():
    """The case the snapshot could not previously see: same script row, same
    version number, different code."""
    before = _script({"specs/x.spec.ts": "await page.goto('/');"})
    after = _script({"specs/x.spec.ts": "await page.goto('/evil');"})
    assert compiled_bundle_digest(before) != compiled_bundle_digest(after)


def test_digest_changes_when_a_file_is_added():
    a = _script({"specs/x.spec.ts": "1"})
    b = _script({"specs/x.spec.ts": "1", "utils/apiClient.ts": "2"})
    assert compiled_bundle_digest(a) != compiled_bundle_digest(b)


def test_absent_script_or_bundle_has_no_digest():
    """A member with nothing to execute is already BLOCKED on other grounds; it
    must not acquire a digest that would later look like drift."""
    assert compiled_bundle_digest(None) is None
    assert compiled_bundle_digest(_script({})) is None
    assert compiled_bundle_digest(_script(None)) is None
