"""Duplicate detection over content, not titles.

The bug: "Duplicate Candidates" read 0 while a depth-1 portal crawl had derived
the same two facts eleven times. Detection was exact lowercased title equality
computed in the browser, and the model titles each restatement differently, so
the one operation that reliably manufactures duplicates was the one it could
not see.

The strings in `NAV_*` and `SOCIAL_*` below are real output from that crawl
against the local fixture, trimmed but not reworded.
"""
from __future__ import annotations

import pytest

from app.services.requirement_duplicates import (
    DEFAULT_THRESHOLD,
    duplicate_requirement_ids,
    find_duplicate_pairs,
    fingerprint,
    group_duplicates,
    jaccard,
    score_pair,
    tokenize,
)


def _req(rid: int, display: str, title: str, criteria: list[str], description: str = ""):
    return {
        "id": rid,
        "requirement_id": display,
        "title": title,
        "acceptance_criteria": criteria,
        "description": description,
    }


NAV_CRITERIA = [
    "Clicking the 'Home' link navigates to http://static-test/index.html and displays the Home Page content.",
    "Clicking the 'About' link navigates to http://static-test/about.html and displays the About Page content.",
    "Clicking the 'Services' link navigates to http://static-test/services.html and displays the Services Page content.",
    "The URL in the browser address bar matches the expected target after each click.",
]
NAV_CRITERIA_REWORDED = [
    "Selecting 'Home' in the primary navigation loads http://static-test/index.html in the same tab.",
    "Selecting 'About' in the primary navigation loads http://static-test/about.html in the same tab.",
    "Selecting 'Services' in the primary navigation loads http://static-test/services.html in the same tab.",
    "The address bar shows the expected target URL after each click.",
]
SOCIAL_CRITERIA = [
    "Clicking the 'LinkedIn' link does not change the current page URL or content; no navigation occurs.",
    "Clicking the 'Twitter' link does not change the current page URL or content; no navigation occurs.",
    "Each placeholder link has href=\"#\" and does not trigger a page load or redirect.",
]
FORM_CRITERIA = [
    "Submitting the contact form with a valid name and email address stores the enquiry.",
    "Submitting with an empty required field shows a validation message and does not submit.",
]


# ── The regression ────────────────────────────────────────────────────────────

def test_the_same_fact_titled_three_ways_is_one_candidate_group():
    """The exact failure: three different titles, one fact, previously invisible."""
    reqs = [
        _req(1, "REQ-0288", "Navigation Links on Landing Page", NAV_CRITERIA),
        _req(2, "REQ-0290", "Navigation Links Lead to Corresponding Real Pages", NAV_CRITERIA),
        _req(3, "REQ-0292", "Primary Navigation Links Navigate to Correct Pages", NAV_CRITERIA_REWORDED),
    ]
    groups = group_duplicates(find_duplicate_pairs(reqs))
    assert groups == [[1, 2, 3]]


def test_title_equality_alone_would_have_found_nothing_here():
    """Guards the premise: no two of these titles are equal, so the detector
    this replaces scores zero on the case it exists for."""
    titles = {
        "Navigation Links on Landing Page",
        "Navigation Links Lead to Corresponding Real Pages",
        "Primary Navigation Links Navigate to Correct Pages",
    }
    assert len(titles) == 3


def test_distinct_requirements_from_the_same_crawl_stay_separate():
    """A contact form and a navigation bar share a site, a vocabulary and a
    source URL. They are not the same requirement."""
    reqs = [
        _req(1, "REQ-0290", "Navigation Links Lead to Corresponding Real Pages", NAV_CRITERIA),
        _req(2, "REQ-0299", "Contact Form Submission and Validation", FORM_CRITERIA),
    ]
    assert find_duplicate_pairs(reqs) == []


def test_navigation_and_social_link_requirements_are_not_paired():
    """Both are about links in a page chrome and share heavy vocabulary, but
    one asserts navigation happens and the other that it does not — opposite
    claims, and the pair that a lower threshold would wrongly merge."""
    reqs = [
        _req(1, "REQ-0290", "Navigation Links Lead to Corresponding Real Pages", NAV_CRITERIA),
        _req(2, "REQ-0291", "Social Media Links Are Inert Placeholders", SOCIAL_CRITERIA),
    ]
    assert find_duplicate_pairs(reqs) == []


# ── Scoring behaviour ─────────────────────────────────────────────────────────

def test_identical_content_scores_one():
    a = fingerprint(_req(1, "R-1", "Navigation works", NAV_CRITERIA))
    b = fingerprint(_req(2, "R-2", "Navigation works", NAV_CRITERIA))
    assert score_pair(a, b).score == pytest.approx(1.0)


def test_criteria_outweigh_titles():
    """The lesson of the bug, encoded: matching titles with unrelated criteria
    must score below differing titles with matching criteria."""
    same_title = score_pair(
        fingerprint(_req(1, "R-1", "Navigation Links Work", NAV_CRITERIA)),
        fingerprint(_req(2, "R-2", "Navigation Links Work", FORM_CRITERIA)),
    )
    same_criteria = score_pair(
        fingerprint(_req(3, "R-3", "Header Menu Destinations", NAV_CRITERIA)),
        fingerprint(_req(4, "R-4", "Primary Nav Targets", NAV_CRITERIA)),
    )
    assert same_criteria.score > same_title.score


def test_an_empty_field_is_not_a_match():
    """Two requirements that both lack a description have nothing in common on
    that axis. Scoring empty-vs-empty as identical would pair everything."""
    assert jaccard(frozenset(), frozenset()) == 0.0


def test_missing_descriptions_do_not_cap_the_score():
    """Weights renormalize over populated fields, so identical requirements
    with no description still reach 1.0 rather than the 0.80 the description
    weight would otherwise withhold."""
    a = fingerprint(_req(1, "R-1", "Same title", NAV_CRITERIA, description=""))
    b = fingerprint(_req(2, "R-2", "Same title", NAV_CRITERIA, description=""))
    assert score_pair(a, b).score == pytest.approx(1.0)


def test_a_requirement_is_never_paired_with_itself():
    reqs = [_req(1, "REQ-1", "Navigation Links", NAV_CRITERIA)]
    assert find_duplicate_pairs(reqs) == []


# ── Normalization ─────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "left, right",
    [
        ("navigation", "navigate"),
        ("navigates", "navigation"),
        ("links", "link"),
        ("pages", "page"),
        ("placeholders", "placeholder"),
    ],
)
def test_word_forms_of_one_concept_collapse(left, right):
    """"Navigation Links" and "Navigate to Link" describe one behaviour."""
    assert tokenize(left) == tokenize(right)


def test_short_words_survive_stemming():
    """A suffix is only stripped when enough stem remains — otherwise "lead"
    becomes "la" and collides with unrelated words."""
    assert tokenize("lead") == frozenset({"lead"})


def test_stopwords_and_punctuation_are_dropped():
    assert tokenize("The link, to the page.") == tokenize("link page")


def test_case_and_ordering_do_not_matter():
    assert tokenize("Home Link Works") == tokenize("works link HOME")


# ── Shape of the output ───────────────────────────────────────────────────────

def test_pairs_are_ordered_strongest_first():
    reqs = [
        _req(1, "REQ-1", "Navigation Links Lead to Pages", NAV_CRITERIA),
        _req(2, "REQ-2", "Navigation Links Lead to Pages", NAV_CRITERIA),
        _req(3, "REQ-3", "Primary Navigation Targets", NAV_CRITERIA_REWORDED),
    ]
    scores = [p.score for p in find_duplicate_pairs(reqs)]
    assert scores == sorted(scores, reverse=True)


def test_every_candidate_carries_a_reason_a_reviewer_can_read():
    """A bare number is not a finding. Each pair states which signal fired."""
    reqs = [
        _req(1, "REQ-1", "Navigation Links on Landing Page", NAV_CRITERIA),
        _req(2, "REQ-2", "Navigation Links Lead to Correct Pages", NAV_CRITERIA),
    ]
    pair = find_duplicate_pairs(reqs)[0]
    assert pair.reason
    assert pair.as_dict()["reason"] == pair.reason
    assert pair.shared_terms


def test_reworded_duplicates_are_reported_as_such():
    """The reason must distinguish "same words" from "same meaning, different
    words" — they call for different reviewer judgement."""
    pair = score_pair(
        fingerprint(_req(1, "R-1", "Header Menu Destinations", NAV_CRITERIA)),
        fingerprint(_req(2, "R-2", "Primary Nav Targets", NAV_CRITERIA)),
    )
    assert "criteria" in pair.reason.lower()


def test_flagged_ids_cover_both_sides_of_every_pair():
    reqs = [
        _req(1, "REQ-1", "Navigation Links on Landing Page", NAV_CRITERIA),
        _req(2, "REQ-2", "Navigation Links Lead to Correct Pages", NAV_CRITERIA),
        _req(3, "REQ-3", "Contact Form Submission and Validation", FORM_CRITERIA),
    ]
    assert duplicate_requirement_ids(find_duplicate_pairs(reqs)) == {1, 2}


def test_five_restatements_are_one_group_not_ten_decisions():
    """A reviewer settles a subject once. Pairwise output would ask them the
    same question ten times."""
    reqs = [_req(i, f"REQ-{i}", f"Navigation Variant {i}", NAV_CRITERIA) for i in range(1, 6)]
    assert group_duplicates(find_duplicate_pairs(reqs)) == [[1, 2, 3, 4, 5]]


def test_separate_subjects_form_separate_groups():
    reqs = [
        _req(1, "REQ-1", "Navigation Links on Landing Page", NAV_CRITERIA),
        _req(2, "REQ-2", "Navigation Links Lead to Correct Pages", NAV_CRITERIA),
        _req(3, "REQ-3", "Social Media Links Are Inert", SOCIAL_CRITERIA),
        _req(4, "REQ-4", "Placeholder Social Links Do Not Navigate", SOCIAL_CRITERIA),
    ]
    assert group_duplicates(find_duplicate_pairs(reqs)) == [[1, 2], [3, 4]]


# ── Robustness ────────────────────────────────────────────────────────────────

def test_criteria_supplied_as_objects_are_flattened():
    """Acceptance criteria have arrived as dicts from some generators; a repr
    like "{'text': ...}" would tokenize into noise."""
    a = _req(1, "R-1", "Navigation", [{"text": c} for c in NAV_CRITERIA])
    b = _req(2, "R-2", "Navigation", NAV_CRITERIA)
    assert score_pair(fingerprint(a), fingerprint(b)).criteria_similarity == pytest.approx(1.0)


def test_missing_and_null_fields_do_not_raise():
    reqs = [
        {"id": 1, "requirement_id": "R-1", "title": None, "acceptance_criteria": None},
        {"id": 2, "requirement_id": "R-2"},
    ]
    assert find_duplicate_pairs(reqs) == []


def test_an_empty_project_has_no_candidates():
    assert find_duplicate_pairs([]) == []
    assert group_duplicates([]) == []


def test_the_threshold_is_configurable_per_call():
    reqs = [
        _req(1, "REQ-1", "Navigation Links Lead to Corresponding Real Pages", NAV_CRITERIA),
        _req(2, "REQ-2", "Social Media Links Are Inert Placeholders", SOCIAL_CRITERIA),
    ]
    assert find_duplicate_pairs(reqs, threshold=DEFAULT_THRESHOLD) == []
    assert find_duplicate_pairs(reqs, threshold=0.05)
