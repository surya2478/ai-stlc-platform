"""Duplicate-candidate detection over requirement content.

Replaces an exact-lowercased-title match that lived in the frontend. That test
found nothing on the case that actually produces duplicates: a portal crawl.
Every page of a site carries the same header and footer, so a depth-1 crawl
derives the same fact once per page — and the model titles each one differently
("Navigation Links Lead to Corresponding Real Pages", "Navigation Links Lead to
Correct Pages", "Primary Navigation Links Navigate to Correct Pages"). Title
equality sees three unrelated requirements; a human sees one fact three times.

Deliberately lexical and deterministic rather than embedding-based. Duplicate
findings gate analysis status and appear as review blockers, so the same inputs
must always produce the same verdict — a score that drifts when an embedding
model is swapped would make a governance decision unreproducible. It also keeps
detection working when no LLM provider is reachable.

**Candidates, never conclusions.** Nothing here merges or deletes. Two
requirements about genuinely different pages can score highly and still both be
wanted; only a reviewer can tell. The output is an ordered list of pairs with
the evidence for each, so the decision stays with a person.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence

# Words carrying no discriminating signal in requirement prose. Kept small and
# generic on purpose: dropping domain words ("navigation", "link") would erase
# exactly the signal that identifies these duplicates.
_STOPWORDS = frozenset("""
a an the and or but if then else when while of to in on at by for with without
from into onto up down out over under again further is are was were be been
being have has had do does did doing will would shall should can could may
might must this that these those it its as not no nor so than too very each
every both all any some such only own same other another
""".split())

# Ordered longest-first so "ation" is tried before "s". A suffix is only removed
# when at least this many characters remain, which stops "lead" -> "la".
_SUFFIXES = (
    "ations", "ation", "ates", "ate", "ings", "ing", "ions", "ion",
    "ers", "er", "ies", "ied", "es", "ed", "ly", "s", "e",
)
_MIN_STEM = 4

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Field weights. Acceptance criteria dominate because they are the testable
# substance: two requirements asserting the same criteria are the same
# requirement however differently they are titled. Titles are the weakest
# signal here, which is the whole lesson of the bug this replaces.
_WEIGHT_CRITERIA = 0.55
_WEIGHT_TITLE = 0.25
_WEIGHT_DESCRIPTION = 0.20

# Score at or above which a pair is offered to a reviewer.
#
# Measured, not guessed. Against the 14 requirements a depth-1 crawl produced
# for project 11 — two facts restated eleven times, plus three genuinely
# distinct requirements — the two populations separate cleanly:
#
#   distinct pairs        peak at 0.168  (Contact Form ~ Accessibility)
#   restatements of a fact run 0.39 - 0.72
#
# 0.40 sits in that gap. On that sample it produced ten candidate pairs, all
# ten correct, forming exactly the two groups a human would draw. It misses two
# of the weaker restatements (0.32-0.35), which is the intended trade: a false
# positive costs a reviewer a real decision on a real pair, while a threshold
# low enough to catch everything starts pairing navigation requirements with
# social-link ones at 0.29.
DEFAULT_THRESHOLD = 0.40

MAX_PAIRS = 200


def _stem(word: str) -> str:
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= _MIN_STEM:
            return word[: -len(suffix)]
    return word


def tokenize(text: str) -> frozenset[str]:
    """Normalized content words. Set semantics: word order carries no meaning
    for "are these the same requirement", and repetition would let one verbose
    field dominate."""
    if not text:
        return frozenset()
    return frozenset(
        _stem(t)
        for t in _TOKEN_RE.findall(str(text).lower())
        if t not in _STOPWORDS and len(t) > 1
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    """Overlap as a fraction of combined vocabulary.

    Two empty fields score 0.0, not 1.0: "both said nothing" is not evidence of
    sameness, and scoring it as a perfect match would flag every pair of
    requirements that happen to lack a description.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass(frozen=True)
class RequirementFingerprint:
    """The comparable content of one requirement."""

    requirement_id: int
    display_id: str
    title: str
    title_tokens: frozenset[str] = frozenset()
    criteria_tokens: frozenset[str] = frozenset()
    description_tokens: frozenset[str] = frozenset()

    @property
    def all_tokens(self) -> frozenset[str]:
        return self.title_tokens | self.criteria_tokens | self.description_tokens


@dataclass
class DuplicatePair:
    """One candidate, with the evidence a reviewer needs to judge it."""

    left_id: int
    right_id: int
    left_display_id: str
    right_display_id: str
    score: float
    title_similarity: float
    criteria_similarity: float
    description_similarity: float
    shared_terms: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "left_id": self.left_id,
            "right_id": self.right_id,
            "left_display_id": self.left_display_id,
            "right_display_id": self.right_display_id,
            "score": round(self.score, 4),
            "title_similarity": round(self.title_similarity, 4),
            "criteria_similarity": round(self.criteria_similarity, 4),
            "description_similarity": round(self.description_similarity, 4),
            "shared_terms": self.shared_terms,
            "reason": self.reason,
        }

    @property
    def reason(self) -> str:
        """Why this pair surfaced, in the reviewer's terms — never a bare score.

        Names the dominant signal so "these are the same fact worded twice" is
        distinguishable at a glance from "these share a title but assert
        different things".
        """
        if self.criteria_similarity >= 0.8:
            return "Acceptance criteria are near-identical."
        if self.criteria_similarity >= 0.5 and self.title_similarity < 0.5:
            return "Different wording, but the acceptance criteria largely overlap."
        if self.title_similarity >= 0.8:
            return "Titles are near-identical."
        return "Titles and acceptance criteria overlap substantially."


def _as_text(value: Any) -> str:
    """Flatten a field that may be a string, a list, or a list of dicts."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return " ".join(str(v) for v in value.values() if v)
    if isinstance(value, Iterable):
        return " ".join(_as_text(v) for v in value)
    return str(value)


def fingerprint(requirement: Any) -> RequirementFingerprint:
    """Build a fingerprint from an ORM row or a plain dict."""

    def get(name: str) -> Any:
        if isinstance(requirement, dict):
            return requirement.get(name)
        return getattr(requirement, name, None)

    return RequirementFingerprint(
        requirement_id=get("id"),
        display_id=str(get("requirement_id") or ""),
        title=str(get("title") or ""),
        title_tokens=tokenize(get("title")),
        criteria_tokens=tokenize(_as_text(get("acceptance_criteria"))),
        description_tokens=tokenize(_as_text(get("description"))),
    )


def score_pair(left: RequirementFingerprint, right: RequirementFingerprint) -> DuplicatePair:
    title_sim = jaccard(left.title_tokens, right.title_tokens)
    criteria_sim = jaccard(left.criteria_tokens, right.criteria_tokens)
    desc_sim = jaccard(left.description_tokens, right.description_tokens)

    # Renormalize over the fields both sides actually populate. Without this a
    # pair of identical requirements that carry no description is capped at
    # 0.80, and a threshold set for populated data silently stops working on
    # sparse data.
    weighted, total_weight = 0.0, 0.0
    for sim, weight, present in (
        (criteria_sim, _WEIGHT_CRITERIA, left.criteria_tokens and right.criteria_tokens),
        (title_sim, _WEIGHT_TITLE, left.title_tokens and right.title_tokens),
        (desc_sim, _WEIGHT_DESCRIPTION, left.description_tokens and right.description_tokens),
    ):
        if present:
            weighted += sim * weight
            total_weight += weight
    score = (weighted / total_weight) if total_weight else 0.0

    shared = sorted(left.all_tokens & right.all_tokens)
    return DuplicatePair(
        left_id=left.requirement_id,
        right_id=right.requirement_id,
        left_display_id=left.display_id,
        right_display_id=right.display_id,
        score=score,
        title_similarity=title_sim,
        criteria_similarity=criteria_sim,
        description_similarity=desc_sim,
        shared_terms=shared[:12],
    )


def find_duplicate_pairs(
    requirements: Sequence[Any], *, threshold: float = DEFAULT_THRESHOLD
) -> list[DuplicatePair]:
    """Candidate pairs, highest score first.

    Pairs are generated from an inverted index rather than by comparing every
    requirement with every other: only requirements sharing at least one content
    term are scored. A full O(n²) sweep is fine for a demo project and quietly
    unusable on a real backlog, and two requirements with no shared vocabulary
    cannot clear any sensible threshold anyway.
    """
    prints = [fingerprint(r) for r in requirements if fingerprint(r).requirement_id is not None]
    by_token: dict[str, list[int]] = {}
    for index, fp in enumerate(prints):
        for token in fp.all_tokens:
            by_token.setdefault(token, []).append(index)

    seen: set[tuple[int, int]] = set()
    for indices in by_token.values():
        # A term appearing in nearly every requirement (the product name, say)
        # generates pairs without discriminating between them; the score still
        # decides, this only avoids materializing the pairs.
        if len(indices) > 60:
            continue
        for i, left in enumerate(indices):
            for right in indices[i + 1:]:
                seen.add((left, right) if left < right else (right, left))

    pairs = []
    for left, right in seen:
        pair = score_pair(prints[left], prints[right])
        if pair.score >= threshold:
            pairs.append(pair)

    pairs.sort(key=lambda p: (-p.score, p.left_display_id, p.right_display_id))
    return pairs[:MAX_PAIRS]


def duplicate_requirement_ids(pairs: Sequence[DuplicatePair]) -> set[int]:
    """Every requirement appearing in at least one candidate pair."""
    ids: set[int] = set()
    for pair in pairs:
        ids.add(pair.left_id)
        ids.add(pair.right_id)
    return ids


def group_duplicates(pairs: Sequence[DuplicatePair]) -> list[list[int]]:
    """Connected components over the candidate pairs.

    Five restatements of one fact are one thing for a reviewer to settle, not
    ten independent pairwise decisions. Transitivity is not guaranteed by the
    scoring — A~B and B~C does not prove A~C — but grouping them for *review*
    is right even so: they are all about the same subject.
    """
    parent: dict[int, int] = {}

    def find(x: int) -> int:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for pair in pairs:
        union(pair.left_id, pair.right_id)

    groups: dict[int, list[int]] = {}
    for node in parent:
        groups.setdefault(find(node), []).append(node)
    return sorted((sorted(g) for g in groups.values() if len(g) > 1), key=lambda g: g[0])
