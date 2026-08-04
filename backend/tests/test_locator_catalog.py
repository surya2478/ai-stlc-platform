"""The catalog generation grounds against.

The behaviour under test is the one that gives publishing an Application Model
any effect: a published model replaces `locator_map` as the source, a
reviewer's "unstable" verdict removes an element from generation, and a
project with no published model generates exactly as it did before.

Same queued-response fake DB pattern as test_application_model_service.py.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import anyio

from app.services import locator_catalog


class _ScalarsResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return list(self._values)


class _ExecuteResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsResult(self._values)

    def scalar_one_or_none(self):
        return self._values[0] if self._values else None


class _FakeDB:
    def __init__(self, execute_queue):
        self.execute_queue = list(execute_queue)

    async def execute(self, _stmt):
        values = self.execute_queue.pop(0) if self.execute_queue else []
        return _ExecuteResult(values)


_T0 = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)


def _evidence(*, node_id=1, locator="#submit", locator_type="css", confidence=95,
              status="candidate", age_seconds=0, row_id=1):
    return SimpleNamespace(
        id=row_id, node_id=node_id, locator_value=locator, locator_type=locator_type,
        confidence=confidence, status=status, created_at=_T0 + timedelta(seconds=age_seconds),
    )


def _element(*, node_id=1, external_ref="element-submit", display_name="Click Submit",
             description=None, parent_node_id=None, attributes=None, evidence=None):
    return SimpleNamespace(
        id=node_id, node_type="element", external_ref=external_ref, display_name=display_name,
        description=description, parent_node_id=parent_node_id,
        attributes=attributes if attributes is not None else {},
        locator_evidence=evidence or [],
    )


def _screen(*, node_id=90, external_ref="screen-shop-example-com-checkout"):
    return SimpleNamespace(
        id=node_id, node_type="screen", external_ref=external_ref, display_name=external_ref,
        description=None, parent_node_id=None, attributes={}, locator_evidence=[],
    )


def _published_model(model_id=7, version=3):
    return SimpleNamespace(id=model_id, version=version, status="published")


def _map_row(element_name="button_submit", page="https://shop.example.com/checkout"):
    return SimpleNamespace(
        element_name=element_name, page=page, recommended_strategy="role",
        business_meaning="submits the order", recommended_locator="getByRole('button')",
        confidence_score=70,
    )


def _build(execute_queue, application_id=1):
    db = _FakeDB(execute_queue)
    return anyio.run(
        lambda: locator_catalog.build_for_application(db, project_id=1, application_id=application_id)
    )


def test_a_published_model_is_the_source_not_locator_map():
    node = _element(
        attributes={"catalog_name": "button_submit", "page_url": "https://shop.example.com/checkout"},
        evidence=[_evidence()],
    )
    catalog = _build([[_published_model()], [node]])

    assert catalog.source == "application_model"
    assert catalog.model_id == 7
    assert catalog.model_version == 3
    assert catalog.entries == [{
        "element_name": "button_submit",
        "page": "https://shop.example.com/checkout",
        "role": "css",
        "business_meaning": "Click Submit",
        "recommended_locator": "#submit",
        "confidence_score": 95,
    }]


def test_no_published_model_falls_back_to_locator_map_unchanged():
    """The path every project without a model still takes."""
    catalog = _build([[], [_map_row()]])

    assert catalog.source == "locator_map"
    assert catalog.model_id is None
    assert catalog.entries == [{
        "element_name": "button_submit",
        "page": "https://shop.example.com/checkout",
        "role": "role",
        "business_meaning": "submits the order",
        "recommended_locator": "getByRole('button')",
        "confidence_score": 70,
    }]


def test_an_element_a_reviewer_marked_unstable_is_not_generated_against():
    """The whole point of grounding on the reviewed artefact."""
    node = _element(evidence=[
        _evidence(row_id=1, locator="#submit", status="candidate", age_seconds=0),
        _evidence(row_id=2, locator="#submit", status="unstable", age_seconds=60),
    ])
    # Model yields nothing usable, so it falls back rather than shipping empty.
    catalog = _build([[_published_model()], [node], [_map_row()]])

    assert catalog.source == "locator_map"
    assert catalog.model_id == 7  # still reports which model was consulted


def test_a_fallback_added_after_an_unstable_verdict_is_used():
    node = _element(
        attributes={"catalog_name": "button_submit"},
        evidence=[
            _evidence(row_id=1, locator="#submit", status="candidate", age_seconds=0),
            _evidence(row_id=2, locator="#submit", status="unstable", age_seconds=60),
            _evidence(row_id=3, locator="[data-testid=submit]", locator_type="testid",
                      status="fallback", age_seconds=120),
        ],
    )
    catalog = _build([[_published_model()], [node]])

    assert catalog.source == "application_model"
    assert catalog.entries[0]["recommended_locator"] == "[data-testid=submit]"
    assert catalog.entries[0]["role"] == "testid"


def test_the_newest_confirmed_locator_wins_over_older_rows():
    """Evidence is append-only — the latest row is the current recommendation."""
    node = _element(
        attributes={"catalog_name": "button_submit"},
        evidence=[
            _evidence(row_id=1, locator="#old", age_seconds=0),
            _evidence(row_id=2, locator="#new", status="confirmed", age_seconds=90),
        ],
    )
    catalog = _build([[_published_model()], [node]])

    assert catalog.entries[0]["recommended_locator"] == "#new"


def test_an_element_with_no_locator_at_all_is_skipped():
    node = _element(evidence=[_evidence(locator=None, locator_type=None)])
    catalog = _build([[_published_model()], [node], []])

    assert catalog.entries == []
    assert catalog.source == "none"


def test_an_older_model_without_page_url_falls_back_to_its_screen_reference():
    """Models built before the page URL was captured still produce a catalog."""
    screen = _screen()
    node = _element(parent_node_id=screen.id, evidence=[_evidence()])
    catalog = _build([[_published_model()], [node, screen]])

    assert catalog.entries[0]["page"] == "screen-shop-example-com-checkout"
    # No catalog_name recorded either — the element ref, minus its prefix.
    assert catalog.entries[0]["element_name"] == "submit"


def test_a_test_case_with_no_application_gets_no_catalog():
    catalog = _build([], application_id=None)

    assert catalog.entries == []
    assert catalog.source == "none"


# --- What the studio is told ------------------------------------------------


def test_the_reported_source_distinguishes_a_model_that_contributed_nothing():
    """A published model that grounds nothing must not read as grounded.

    This is the case the studio could not previously see: it inferred grounding
    from the existence of a published model, so a model whose every element was
    marked unstable looked identical to one backing the whole catalog.
    """
    node = _element(evidence=[
        _evidence(row_id=1, status="candidate", age_seconds=0),
        _evidence(row_id=2, status="unstable", age_seconds=60),
    ])
    catalog = _build([[_published_model()], [node], [_map_row()]])

    # A model exists and is published...
    assert catalog.model_id == 7
    assert catalog.model_version == 3
    # ...but it is not what the script will be built from.
    assert catalog.source == "locator_map"
    assert len(catalog.entries) == 1


# ── The model fills what it knows, locator_map fills the rest ────────────────
#
# The model used to win outright. It holds one element per step discovery
# ACTED ON; locator_map holds everything the page crawl saw. Live on project
# 14 that was 1 element against 97, so publishing a model shrank the catalog by
# two orders of magnitude and assertions were dropped for want of a target.
# Merging is safe because model nodes carry `catalog_name` — the locator_map
# key — so both stores are keyed in one namespace.


def test_the_map_fills_elements_the_model_does_not_have():
    node = _element(
        attributes={"catalog_name": "button_submit", "page_url": "https://shop.example.com/checkout"},
        evidence=[_evidence()],
    )
    catalog = _build([[_published_model()], [node], [_map_row(element_name="button_add_to_cart")]])

    assert catalog.source == "application_model+locator_map"
    assert [e["element_name"] for e in catalog.entries] == ["button_submit", "button_add_to_cart"]
    # Provenance still points at the model that contributed.
    assert catalog.model_id == 7
    assert catalog.model_version == 3


def test_the_reviewed_locator_wins_where_both_stores_know_the_element():
    """No double-naming: one entry per catalog_name, the reviewed one."""
    node = _element(
        attributes={"catalog_name": "button_submit", "page_url": "https://shop.example.com/checkout"},
        evidence=[_evidence(locator="#reviewed")],
    )
    catalog = _build([[_published_model()], [node], [_map_row(element_name="button_submit")]])

    assert catalog.source == "application_model"
    assert len(catalog.entries) == 1
    assert catalog.entries[0]["recommended_locator"] == "#reviewed"


def test_the_reviewer_veto_is_not_undone_by_the_map():
    """The one way merging could have gone wrong.

    An element ruled unstable yields no model entry. If `locator_map` still
    carries that element under the same name, filling the gap from the map
    would quietly reinstate exactly the locator a human rejected.
    """
    node = _element(
        attributes={"catalog_name": "button_submit"},
        evidence=[
            _evidence(row_id=1, locator="#submit", status="candidate", age_seconds=0),
            _evidence(row_id=2, locator="#submit", status="unstable", age_seconds=60),
        ],
    )
    catalog = _build([[_published_model()], [node], [_map_row(element_name="button_submit")]])

    assert catalog.entries == []
    assert catalog.source == "none"


def test_a_veto_suppresses_only_the_element_it_names():
    """Other elements still come through — a veto is not a blanket refusal."""
    rejected = _element(
        node_id=1, attributes={"catalog_name": "button_submit"},
        evidence=[
            _evidence(row_id=1, locator="#submit", status="candidate", age_seconds=0),
            _evidence(row_id=2, locator="#submit", status="unstable", age_seconds=60),
        ],
    )
    catalog = _build([
        [_published_model()], [rejected],
        [_map_row(element_name="button_submit"), _map_row(element_name="button_add_to_cart")],
    ])

    assert [e["element_name"] for e in catalog.entries] == ["button_add_to_cart"]
    assert catalog.source == "locator_map"
