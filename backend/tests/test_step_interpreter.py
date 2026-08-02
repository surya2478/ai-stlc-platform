"""Guided discovery performs the step it recorded.

Found on session #21 against the local fixture: three steps were captured as
`action_family="read"` with no screen or element reference, and the browser was
never touched. Every screenshot showed the landing page, including the one
stored as evidence for "Click the 'Home' link". The capture was genuine; the
label on it was not, and the Application Model built from it was empty.

The rule these tests exist to hold: a step is performed only when its own words
say unambiguously what to do and the page unambiguously offers it. Everything
else degrades to an honest observation. A wrong click is worse than no click,
because it looks deliberate.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.discovery.step_interpreter import (
    interpret_step,
    resolve_target_ref,
    screen_ref_for,
)


def _el(role, name, ref):
    return SimpleNamespace(role=role, name=name, ref=ref)


def _snapshot(elements, page_url="http://static-test/services.html"):
    return SimpleNamespace(page_url=page_url, elements=elements)


# ── The steps that failed ─────────────────────────────────────────────────────

def test_the_click_step_that_was_recorded_as_a_read():
    """Verbatim from TC-0069, the step whose evidence was a screenshot of a
    page no click had been performed on."""
    step = interpret_step("Click the 'Home' link (href='index.html')")
    assert step.action_family == "click"
    assert step.target_label == "Home"


def test_the_navigate_step_that_never_navigated():
    step = interpret_step("Navigate to http://static-test/services.html")
    assert step.action_family == "navigate"
    assert step.url == "http://static-test/services.html"


def test_the_verify_step_is_genuinely_a_read():
    """Not every step was mislabelled — this one was right, and must stay so."""
    step = interpret_step("Verify HTTP response status for index.html is 200")
    assert step.action_family == "read"


# ── Classification ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "Click the Submit button",
    "Press the Continue button",
    "Select the 'Services' tab",
    "Tap the Menu icon",
])
def test_interaction_verbs_become_clicks(text):
    assert interpret_step(text).action_family == "click"


@pytest.mark.parametrize("text, url", [
    ("Go to https://example.com/login", "https://example.com/login"),
    ("Open the page at http://static-test/about.html", "http://static-test/about.html"),
    ("Visit https://example.com/a?b=c", "https://example.com/a?b=c"),
])
def test_navigation_needs_a_real_address(text, url):
    step = interpret_step(text)
    assert step.action_family == "navigate"
    assert step.url == url


def test_navigation_without_an_address_is_not_invented():
    """"Navigate to the services page" names no URL. Deriving one from the base
    URL by convention is exactly the guess that makes a run unverifiable."""
    step = interpret_step("Navigate to the services page")
    assert step.action_family == "read"
    assert step.url is None


def test_input_needs_both_a_value_and_a_field():
    step = interpret_step("Enter 'jane@example.com' in the Email field")
    assert step.action_family == "input"
    assert step.input_text == "jane@example.com"
    assert step.target_label == "Email"


def test_input_without_a_value_is_not_performed():
    assert interpret_step("Enter the customer's email address").action_family == "read"


def test_a_click_with_nothing_named_is_not_a_click():
    """"Click the link" identifies nothing. Performing it would mean choosing
    a link on the user's behalf."""
    assert interpret_step("Click the link").action_family == "read"


@pytest.mark.parametrize("text", [
    "Verify the page title is correct",
    "Check that the footer is visible",
    "Assert the URL matches /index.html",
    "Confirm no console errors appear",
    "Observe the loading indicator",
])
def test_assertion_verbs_are_observations(text):
    assert interpret_step(text).action_family == "read"


def test_an_unreadable_step_is_an_observation_not_a_guess():
    assert interpret_step("The system should behave correctly").action_family == "read"
    assert interpret_step("").action_family == "read"
    assert interpret_step(None).action_family == "read"


def test_quoted_labels_win_over_surrounding_prose():
    assert interpret_step('Click the "Contact Us" link in the header').target_label == "Contact Us"


def test_unquoted_labels_are_read_from_the_ui_noun():
    assert interpret_step("Click the Services tab").target_label == "Services"


# ── Target resolution ─────────────────────────────────────────────────────────

def test_one_matching_control_resolves():
    snap = _snapshot([_el("link", "Home", "e1"), _el("link", "About", "e2")])
    assert resolve_target_ref(snap, interpret_step("Click the 'Home' link")) == "e1"


def test_two_controls_with_the_same_name_resolve_to_nothing():
    """A header and a footer "Home" are genuinely ambiguous. Picking the first
    would silently decide something only a person can."""
    snap = _snapshot([_el("link", "Home", "e1"), _el("link", "Home", "e9")])
    assert resolve_target_ref(snap, interpret_step("Click the 'Home' link")) is None


def test_a_click_does_not_resolve_to_a_non_clickable_element():
    """A heading reading "Home" is not the Home link."""
    snap = _snapshot([_el("heading", "Home", "e1"), _el("paragraph", "Home", "e2")])
    assert resolve_target_ref(snap, interpret_step("Click the 'Home' link")) is None


def test_an_input_resolves_only_to_input_roles():
    snap = _snapshot([_el("textbox", "Email", "e1"), _el("link", "Email", "e2")])
    step = interpret_step("Enter 'a@b.com' in the Email field")
    assert resolve_target_ref(snap, step) == "e1"


def test_a_partial_match_resolves_only_when_unique():
    snap = _snapshot([_el("button", "Submit enquiry", "e1")])
    assert resolve_target_ref(snap, interpret_step("Click the 'Submit' button")) == "e1"


def test_an_ambiguous_partial_match_resolves_to_nothing():
    snap = _snapshot([_el("button", "Submit enquiry", "e1"), _el("button", "Submit order", "e2")])
    assert resolve_target_ref(snap, interpret_step("Click the 'Submit' button")) is None


def test_matching_ignores_case_and_spacing():
    snap = _snapshot([_el("link", "  CONTACT   US ", "e1")])
    assert resolve_target_ref(snap, interpret_step("Click the 'contact us' link")) == "e1"


def test_an_element_with_no_ref_is_not_offered():
    snap = _snapshot([_el("link", "Home", None)])
    assert resolve_target_ref(snap, interpret_step("Click the 'Home' link")) is None


def test_nothing_resolves_without_a_snapshot():
    assert resolve_target_ref(None, interpret_step("Click the 'Home' link")) is None


# ── Screen references ─────────────────────────────────────────────────────────
#
# The Application Model builds screen nodes from these alone. Before this, no
# code path set one, so every discovery session produced an empty model.

def test_a_screen_ref_is_derived_from_the_observed_url():
    assert screen_ref_for(_snapshot([], "http://static-test/services.html")) == "screen-static-test-services-html"


def test_the_same_page_always_yields_the_same_ref():
    a = screen_ref_for(_snapshot([], "http://static-test/about.html"))
    b = screen_ref_for(_snapshot([], "http://static-test/about.html?utm=x#top"))
    assert a == b == "screen-static-test-about-html"


def test_different_pages_yield_different_refs():
    assert screen_ref_for(_snapshot([], "http://x/a.html")) != screen_ref_for(_snapshot([], "http://x/b.html"))


def test_two_hosts_are_two_sets_of_screens():
    """One session may touch more than one application."""
    assert screen_ref_for(_snapshot([], "http://a/p")) != screen_ref_for(_snapshot([], "http://b/p"))


def test_a_site_root_still_gets_a_ref():
    assert screen_ref_for(_snapshot([], "http://static-test/")) == "screen-static-test"


def test_no_url_means_no_screen_ref():
    """Better an empty model that says so than a screen node named after
    nothing."""
    assert screen_ref_for(_snapshot([], None)) is None
    assert screen_ref_for(None) is None
