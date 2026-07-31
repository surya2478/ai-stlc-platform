"""Requirement gate semantics — severity, the taxonomy waiver, and resolution routes.

These rules changed after a real project whose requirements were derived from a
crawled URL: every declared unknown blocked, and two taxonomy blockers could not
be satisfied by any re-run because the vocabulary is telecom-only. Pure functions,
so no DB fixture is needed — the same style as test_automation_suite_readiness.py.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services import requirement_blockers as rb


def _req(**overrides):
    base = dict(
        metadata_={"quality_review": {}},
        quality_verdict="pass",
        missing_information=[],
        telecom_domain="Digital",
        qa_domain=None,
        business_process=None,
        product="Broadband",
        product_group=None,
        sub_request_type=None,
        systems_impacted=["Website Frontend"],
        impacted_systems=None,
        impacted_interfaces=None,
        upstream_systems=None,
        downstream_systems=None,
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def _codes(req) -> list[str]:
    return [b.code for b in rb.analysis_blockers(req)]


# ── Normalizing the two shapes ──────────────────────────────────────────────


def test_legacy_bare_string_normalizes_to_blocking():
    """Defaulting old rows to advisory would retroactively unblock requirements
    no agent has actually re-judged."""
    items = rb.normalize_missing_information(["Exact API endpoint and payload"])
    assert items[0].severity == "blocking"
    assert items[0].is_blocking is True


def test_object_form_preserves_severity():
    items = rb.normalize_missing_information(
        [{"item": "Success message wording", "severity": "advisory"}]
    )
    assert items[0].severity == "advisory"
    assert items[0].is_blocking is False


def test_unrecognized_severity_falls_back_to_blocking():
    items = rb.normalize_missing_information([{"item": "x", "severity": "meh"}])
    assert items[0].severity == "blocking"


def test_mixed_legacy_and_new_shapes_are_both_read():
    items = rb.normalize_missing_information(
        ["legacy item", {"item": "new item", "severity": "advisory"}]
    )
    assert [(i.item, i.severity) for i in items] == [
        ("legacy item", "blocking"),
        ("new item", "advisory"),
    ]


def test_blank_and_missing_entries_are_dropped():
    assert rb.normalize_missing_information(["", "  ", {"item": ""}, None]) == []


@pytest.mark.parametrize("value", [None, [], "", {}])
def test_empty_inputs_produce_no_items(value):
    assert rb.normalize_missing_information(value) == []


def test_bare_string_input_is_treated_as_one_item():
    items = rb.normalize_missing_information("a single unwrapped string")
    assert len(items) == 1


# ── Severity actually gates ─────────────────────────────────────────────────


def test_advisory_missing_information_does_not_block():
    """The whole point: cosmetic gaps must not hold up a requirement."""
    req = _req(
        missing_information=[
            {"item": "Success and error message wording", "severity": "advisory"},
            {"item": "Exact button colour", "severity": "advisory"},
        ]
    )
    assert "missing_information" not in _codes(req)
    assert rb.analysis_blockers(req) == []


def test_blocking_missing_information_still_blocks():
    req = _req(
        missing_information=[{"item": "Exact API payload", "severity": "blocking"}]
    )
    assert "missing_information" in _codes(req)


def test_each_blocking_item_is_reported_separately():
    """One aggregated message hid which specific answers were needed."""
    req = _req(
        missing_information=[
            {"item": "Endpoint", "severity": "blocking"},
            {"item": "Validation rule", "severity": "blocking"},
            {"item": "Wording", "severity": "advisory"},
        ]
    )
    missing = [b for b in rb.analysis_blockers(req) if b.code == "missing_information"]
    assert len(missing) == 2
    assert any("Endpoint" in b.message for b in missing)
    assert not any("Wording" in b.message for b in missing)


def test_advisory_items_are_still_surfaced_separately():
    """Not blocking is not the same as hidden."""
    advisory = rb.advisory_missing_information(
        [{"item": "Wording", "severity": "advisory"}, "Endpoint"]
    )
    assert [a.item for a in advisory] == ["Wording"]


# ── Taxonomy waiver ─────────────────────────────────────────────────────────


def test_missing_taxonomy_blocks_by_default():
    req = _req(telecom_domain=None, qa_domain=None, business_process=None, product=None)
    assert "taxonomy_domain" in _codes(req)
    assert "taxonomy_product" in _codes(req)


def test_waiver_clears_both_taxonomy_blockers():
    req = _req(
        telecom_domain=None,
        qa_domain=None,
        business_process=None,
        product=None,
        metadata_={
            "quality_review": {},
            "taxonomy_not_applicable": {
                "reason": "Generic marketing site, no telecom domain applies",
                "by_user_id": 3,
                "at": "2026-07-30T12:00:00Z",
            },
        },
    )
    assert "taxonomy_domain" not in _codes(req)
    assert "taxonomy_product" not in _codes(req)


def test_waiver_does_not_clear_anything_else():
    """It waives taxonomy, not quality or missing information."""
    req = _req(
        quality_verdict="needs_revision",
        missing_information=[{"item": "Endpoint", "severity": "blocking"}],
        telecom_domain=None,
        product=None,
        metadata_={
            "quality_review": {},
            "taxonomy_not_applicable": {"reason": "n/a", "by_user_id": 1, "at": "x"},
        },
    )
    codes = _codes(req)
    assert "quality_not_pass" in codes
    assert "missing_information" in codes


def test_malformed_waiver_is_ignored():
    req = _req(
        telecom_domain=None,
        product=None,
        metadata_={"quality_review": {}, "taxonomy_not_applicable": "yes please"},
    )
    assert "taxonomy_domain" in _codes(req)


# ── Resolution routes ───────────────────────────────────────────────────────


def test_taxonomy_needs_human_input_not_a_rerun():
    """The bug that started this: the panel offered Re-run for something no
    re-run could fix."""
    req = _req(telecom_domain=None, qa_domain=None, business_process=None, product=None)
    taxonomy = [b for b in rb.analysis_blockers(req) if b.code.startswith("taxonomy")]
    assert taxonomy and all(b.resolution == "human_input" for b in taxonomy)


def test_missing_information_routes_to_clarification():
    req = _req(missing_information=[{"item": "Endpoint", "severity": "blocking"}])
    missing = [b for b in rb.analysis_blockers(req) if b.code == "missing_information"]
    assert all(b.resolution == "clarification" for b in missing)


def test_quality_verdict_routes_to_rerun():
    req = _req(quality_verdict="needs_revision")
    assert [b.resolution for b in rb.analysis_blockers(req)] == ["rerun_analysis"]


def test_stale_review_supersedes_the_verdict_blocker():
    """Both would tell the reader to fix a score about to be recalculated."""
    req = _req(
        quality_verdict="needs_revision", metadata_={"quality_review": {"stale": True}}
    )
    codes = _codes(req)
    assert codes == ["quality_stale"]


def test_rerun_cannot_help_is_flagged():
    """A requirement blocked only on human input must say so."""
    req = _req(telecom_domain=None, qa_domain=None, business_process=None, product=None)
    summary = rb.summarize(rb.analysis_blockers(req))
    assert summary["rerun_cannot_help"] is True
    assert summary["by_resolution"]["rerun_analysis"] == []
    assert len(summary["by_resolution"]["human_input"]) == 2


def test_rerun_can_help_when_a_quality_blocker_remains():
    req = _req(quality_verdict="fail", telecom_domain=None, product=None)
    summary = rb.summarize(rb.analysis_blockers(req))
    assert summary["rerun_cannot_help"] is False


def test_clean_requirement_has_no_blockers_and_no_false_flag():
    summary = rb.summarize(rb.analysis_blockers(_req()))
    assert summary["total"] == 0
    assert summary["rerun_cannot_help"] is False


def test_every_blocker_carries_a_human_readable_route():
    req = _req(
        quality_verdict="fail",
        missing_information=["legacy blocking item"],
        telecom_domain=None,
        product=None,
    )
    for blocker in rb.analysis_blockers(req):
        payload = blocker.as_dict()
        assert payload["resolution"] in rb.RESOLUTION_LABEL
        assert payload["resolution_label"]


# ── Traceability adds the mapping requirement ───────────────────────────────


def test_traceability_requires_a_system_mapping():
    req = _req(systems_impacted=None, product=None, product_group=None)
    codes = [b.code for b in rb.traceability_blockers(req)]
    assert "system_mapping" in codes


def test_traceability_mapping_satisfied_by_any_source():
    req = _req(systems_impacted=None, impacted_interfaces=["Diameter Gy"])
    codes = [b.code for b in rb.traceability_blockers(req)]
    assert "system_mapping" not in codes
