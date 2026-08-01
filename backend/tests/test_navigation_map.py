"""Known navigation targets remove the manual URL entry a screenshot forced.

A requirement derived from an uploaded screenshot cannot see hrefs, so it
declared "Exact URLs for each navigation target" as blocking and waited on a
person — for an application the project had already registered a base URL for
and, in the URL-analysis case, already read every anchor from.

The map closes that loop. Its correctness rests on one rule: every destination
must have been *observed*. Deriving "About" -> "/about" from convention would be
wrong precisely where a site is unusual, and wrong silently.
"""
from __future__ import annotations

from app.services.navigation_map import (
    MAX_TARGETS,
    merge_link_inventories,
    normalize_label,
    render_navigation_prompt,
)

INVENTORY = [
    {"label": "Home", "href": "index.html", "url": "https://x.com/index.html"},
    {"label": "About", "href": "about.html", "url": "https://x.com/about.html"},
]


# ── Label normalization ─────────────────────────────────────────────────────


def test_screen_wording_normalizes_onto_markup_wording():
    """A screenshot says "Services Page"; the markup says "Services"."""
    assert normalize_label("Services Page") == "services"
    assert normalize_label("Contact Link") == "contact"
    assert normalize_label("  HOME  ") == "home"


def test_repeated_noise_suffixes_are_all_stripped():
    assert normalize_label("Services Page Link") == "services"


def test_a_label_that_is_entirely_a_noise_word_keeps_its_name():
    """Only a *trailing* noise word is stripped, so a link genuinely labelled
    "Page" stays matchable instead of normalizing to nothing and colliding with
    every other stripped-to-empty label."""
    assert normalize_label("Page") == "page"
    assert normalize_label("Link") == "link"


# ── Merging ─────────────────────────────────────────────────────────────────


def test_targets_carry_the_observed_label_and_url():
    assert merge_link_inventories([INVENTORY]) == [
        {"label": "Home", "url": "https://x.com/index.html"},
        {"label": "About", "url": "https://x.com/about.html"},
    ]


def test_the_same_destination_from_two_pages_appears_once():
    """Header and footer reach the same place; repeating it only pads the
    prompt."""
    out = merge_link_inventories([INVENTORY, INVENTORY])
    assert len(out) == 2


def test_a_link_without_a_destination_is_never_offered_as_known():
    """The whole point is to stop claiming a URL the platform does not have."""
    out = merge_link_inventories([[{"label": "Home", "href": "", "url": ""}]])
    assert out == []


def test_an_unlabelled_destination_is_skipped():
    """It cannot be matched to anything on a screen, so it is noise."""
    assert merge_link_inventories([[{"label": "", "url": "https://x.com/a"}]]) == []


def test_malformed_inventories_are_tolerated():
    assert merge_link_inventories([None, "nope", [None, 3], INVENTORY]) == [
        {"label": "Home", "url": "https://x.com/index.html"},
        {"label": "About", "url": "https://x.com/about.html"},
    ]


def test_the_target_list_is_capped():
    big = [[{"label": f"L{i}", "url": f"https://x.com/{i}"} for i in range(200)]]
    assert len(merge_link_inventories(big)) == MAX_TARGETS


# ── Prompt rendering ────────────────────────────────────────────────────────


def test_nothing_observed_renders_nothing_at_all():
    """An empty heading would read as "this screen has no navigation targets",
    which is a stronger claim than "none have been observed"."""
    assert render_navigation_prompt({}) == ""
    assert render_navigation_prompt({"targets": [], "base_urls": {}}) == ""


def test_observed_targets_and_base_urls_are_both_offered():
    text = render_navigation_prompt({
        "targets": [{"label": "About", "url": "https://x.com/about.html"}],
        "base_urls": {"WebApp (Regression)": "https://x.com/"},
    })
    assert "About -> https://x.com/about.html" in text
    assert "WebApp (Regression): https://x.com/" in text


def test_the_prompt_forbids_inventing_an_unlisted_destination():
    """Without this the model would happily derive /about from the base URL,
    which is the failure mode the whole map exists to avoid."""
    text = render_navigation_prompt({
        "targets": [{"label": "About", "url": "https://x.com/about.html"}],
        "base_urls": {"WebApp": "https://x.com/"},
    })
    assert "do NOT invent a URL" in text
    assert "by convention" in text
    assert "must stay in" in text


def test_the_prompt_stops_known_targets_being_reported_missing():
    text = render_navigation_prompt({"targets": [{"label": "A", "url": "https://x/a"}]})
    assert "Do NOT report a destination listed above as missing information" in text


def test_base_urls_alone_still_render():
    """A project with a registered application but no analysed pages yet still
    benefits from the agent knowing where the app lives."""
    text = render_navigation_prompt({"targets": [], "base_urls": {"WebApp": "https://x.com/"}})
    assert "https://x.com/" in text
    assert "label -> resolved URL" not in text
