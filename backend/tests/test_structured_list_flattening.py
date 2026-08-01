"""String-list fields render objects as text, not as Python reprs.

`ui_pages`, `apis` and friends are typed `list[str]`, but a model asked for a
page *and* its URL answers with objects. The normalizer called `str()` on them,
so `{"name": "Services Page", "url": "https://..."}` was stored verbatim as a
Python repr — single quotes and all — and shown to users that way.

Seen live immediately after the navigation-map change started asking for URLs
alongside page names.
"""
from __future__ import annotations

from app.agents.structured_schemas import RequirementLLMOutput, _string_list


def test_a_name_and_url_object_becomes_readable_text():
    assert _string_list([{"name": "Services Page", "url": "https://x/services.html"}]) == [
        "Services Page (https://x/services.html)"
    ]


def test_alternative_key_names_are_recognised():
    """Models vary the wording; label/href is as common as name/url."""
    assert _string_list([{"label": "Contact", "href": "https://x/contact"}]) == [
        "Contact (https://x/contact)"
    ]


def test_a_name_without_a_url_keeps_just_the_name():
    assert _string_list([{"name": "Home Page"}]) == ["Home Page"]


def test_a_url_without_a_name_keeps_just_the_url():
    assert _string_list([{"url": "https://x/a"}]) == ["https://x/a"]


def test_plain_strings_are_untouched():
    assert _string_list(["Home Page", "Contact Page"]) == ["Home Page", "Contact Page"]


def test_an_unrecognisable_object_falls_back_to_json_not_a_python_repr():
    """JSON at least parses downstream; `{'a': 1}` with single quotes does not."""
    assert _string_list([{"a": 1}]) == ['{"a": 1}']


def test_mixed_entries_are_handled_together():
    assert _string_list([{"name": "A", "url": "u"}, "plain", 42]) == ["A (u)", "plain", "42"]


def test_none_and_scalars_behave():
    assert _string_list(None) == []
    assert _string_list({"name": "Solo", "url": "u"}) == ["Solo (u)"]


def test_the_requirement_schema_stores_navigation_targets_readably():
    """End to end through the model the URL agent actually validates against."""
    req = RequirementLLMOutput.model_validate({
        "title": "Navigation",
        "ui_pages": [
            {"name": "Home Page", "url": "https://x/"},
            {"name": "Services Page", "url": "https://x/services.html"},
        ],
    })
    assert req.ui_pages == [
        "Home Page (https://x/)",
        "Services Page (https://x/services.html)",
    ]
    assert not any("{'" in page for page in req.ui_pages)
