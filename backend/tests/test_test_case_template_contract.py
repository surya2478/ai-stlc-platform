"""Regression coverage for the shared test-case spreadsheet contract."""

from types import SimpleNamespace

import pytest

from app.services.test_case_import_service import _map_headers, _resolve_row
from app.services.test_case_template import (
    TEST_CASE_TEMPLATE_COLUMNS,
    TEST_CASE_TEMPLATE_HEADERS,
)


EXPECTED_HEADERS = [
    "ID",
    "Domain",
    "Channel",
    "Product",
    "Area of Test",
    "Test Case ID",
    "Environment",
    "Sub Request Type",
    "Test Case Objective",
    "Pre-Requisites",
    "Test Steps",
    "Expected Results",
    "ATC Test Case",
    "Test Case Type",
    "Test Case Complexity",
    "Tested By",
    "JIRA ID or PPM",
    "Overall Status",
    "Blocking Snag ID / Other Reason",
    "SIT",
    "Planned Execution Sequence",
    "Critical TC Mapping",
    "Priority",
    "Severity",
    "BDD Scenario",
    "Approval Status",
    "Requirement ID",
    "Requirement Title",
    "Scenario ID",
    "Scenario Title",
    "Test Phase",
    "Product Group",
    "External TC ID",
    "External TC URL",
    "Created At",
]


def test_canonical_headers_match_import_contract():
    assert TEST_CASE_TEMPLATE_HEADERS == EXPECTED_HEADERS
    assert len(TEST_CASE_TEMPLATE_COLUMNS) == 35
    assert _map_headers(TEST_CASE_TEMPLATE_HEADERS) == dict(TEST_CASE_TEMPLATE_COLUMNS)


@pytest.mark.anyio
async def test_platform_columns_round_trip_through_import_resolution():
    class Resolver:
        async def resolve(self, model, value):
            return None

    requirement = SimpleNamespace(id=91, requirement_id="REQ-0263")
    scenario = SimpleNamespace(id=60, scenario_id="TS-0060", requirement_id=91)
    mapped_row = {
        "test_case_id": "TC-0047",
        "test_case_objective": "Verify billing adjustment",
        "priority": "High",
        "severity": "Critical",
        "bdd_scenario": "Given an eligible account",
        "test_phase": "SIT",
        "product_group": "Billing",
        "external_tc_id": "XRAY-47",
        "external_tc_url": "https://example.test/XRAY-47",
        "requirement_display_id": "req-0263",
        "scenario_display_id": "ts-0060",
        "approval_status": "Approved",
        "created_at": "2026-07-28T10:00:00Z",
    }

    resolved, errors, warnings = await _resolve_row(
        Resolver(),
        mapped_row,
        1,
        {"req-0263": requirement},
        {"ts-0060": scenario},
    )

    assert errors == []
    assert resolved["priority"] == "High"
    assert resolved["severity"] == "Critical"
    assert resolved["bdd_scenario"] == "Given an eligible account"
    assert resolved["test_phase"] == "SIT"
    assert resolved["product_group"] == "Billing"
    assert resolved["external_tc_id"] == "XRAY-47"
    assert resolved["external_tc_url"] == "https://example.test/XRAY-47"
    assert resolved["requirement_id"] == 91
    assert resolved["scenario_id"] == 60
    assert any("Approval Status" in warning["message"] for warning in warnings)
    assert any("Created At" in warning["message"] for warning in warnings)
