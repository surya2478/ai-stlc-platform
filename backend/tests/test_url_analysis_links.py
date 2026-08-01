"""Portal URL analysis keeps link destinations, not just link text.

Found on a real project: a requirement derived from https://aicinfotech.com/
carried `missing_information: ["Exact target URLs for each navigation link"]`
as *blocking*, routed to "needs an answer from the requirement owner" — for a
page the platform had rendered with Playwright and read every href from.

The capture layer was correct. `url_analysis_agent` then reduced each link to
`label or href`, which keeps the href only when a link has no text. Real
navigation links have text, so the destination was discarded every time and the
derivation step genuinely had nothing but labels to work with.
"""
from __future__ import annotations

from app.agents.requirement.url_analysis_agent import (
    DERIVE_SYSTEM,
    MAX_LINKS,
    URL_DERIVE_SUFFIX,
    link_inventory,
)

PAGE = "https://example.com/products/"


def test_a_labelled_link_keeps_its_destination():
    """The regression itself: previously `label or href` returned "Home" and
    the URL was gone."""
    out = link_inventory(PAGE, {"links": [{"label": "Home", "href": "/"}]})
    assert out == [{"label": "Home", "href": "/", "url": "https://example.com/"}]


def test_relative_hrefs_resolve_against_the_page():
    """An automated check needs the absolute URL; a human reading markup wants
    the authored one. Both are kept."""
    out = link_inventory(PAGE, {"links": [{"label": "Detail", "href": "detail?id=1"}]})
    assert out[0]["href"] == "detail?id=1"
    assert out[0]["url"] == "https://example.com/products/detail?id=1"


def test_absolute_and_cross_origin_hrefs_pass_through():
    out = link_inventory(
        PAGE, {"links": [{"label": "Docs", "href": "https://docs.other.com/x"}]}
    )
    assert out[0]["url"] == "https://docs.other.com/x"


def test_an_unlabelled_link_still_reports_its_destination():
    """The one case the old code handled — it must not regress the other way."""
    out = link_inventory(PAGE, {"links": [{"label": "", "href": "/icon-only"}]})
    assert out[0]["label"] == ""
    assert out[0]["url"] == "https://example.com/icon-only"


def test_links_without_an_href_are_dropped():
    out = link_inventory(PAGE, {"links": [{"label": "Nowhere", "href": ""}, {"label": "x"}]})
    assert out == []


def test_duplicate_label_and_destination_pairs_collapse():
    """A nav link repeated in the header and the footer is one destination, but
    the same label pointing somewhere else is not."""
    out = link_inventory(
        PAGE,
        {"links": [
            {"label": "About", "href": "/about"},
            {"label": "About", "href": "/about"},
            {"label": "About", "href": "/company/about"},
        ]},
    )
    assert len(out) == 2
    assert {l["url"] for l in out} == {
        "https://example.com/about",
        "https://example.com/company/about",
    }


def test_the_inventory_is_capped():
    out = link_inventory(
        PAGE, {"links": [{"label": f"L{i}", "href": f"/p{i}"} for i in range(100)]}
    )
    assert len(out) == MAX_LINKS


def test_malformed_entries_do_not_break_the_inventory():
    out = link_inventory(PAGE, {"links": ["not-a-dict", None, {"label": "Ok", "href": "/ok"}]})
    assert len(out) == 1 and out[0]["label"] == "Ok"


def test_missing_or_empty_links_key_is_handled():
    assert link_inventory(PAGE, {}) == []
    assert link_inventory(PAGE, {"links": None}) == []


def test_the_derive_prompt_tells_this_agent_the_destinations_are_known():
    """The shared DERIVE_SYSTEM is written for a screenshot and instructs the
    model to declare navigation destinations missing. Without this suffix the
    agent would keep reporting URLs it can plainly see."""
    combined = DERIVE_SYSTEM + URL_DERIVE_SUFFIX
    assert "LIVE rendered page" in combined
    assert "do NOT list navigation targets" in combined
    # The shared instruction survives — the suffix adds to it, not replaces it.
    assert "acceptance_criteria" in combined
