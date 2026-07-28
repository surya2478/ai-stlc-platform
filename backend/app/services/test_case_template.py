"""Canonical test-case spreadsheet contract shared by import and export."""

TEST_CASE_TEMPLATE_COLUMNS: tuple[tuple[str, str], ...] = (
    ("ID", "id"),
    ("Domain", "domain"),
    ("Channel", "channel"),
    ("Product", "product"),
    ("Area of Test", "area_of_test"),
    ("Test Case ID", "test_case_id"),
    ("Environment", "environment"),
    ("Sub Request Type", "sub_request_type"),
    ("Test Case Objective", "test_case_objective"),
    ("Pre-Requisites", "preconditions"),
    ("Test Steps", "steps"),
    ("Expected Results", "expected_result"),
    ("ATC Test Case", "atc_test_case"),
    ("Test Case Type", "test_case_type"),
    ("Test Case Complexity", "test_case_complexity"),
    ("Tested By", "tested_by"),
    ("JIRA ID or PPM", "jira_or_ppm"),
    ("Overall Status", "overall_status"),
    ("Blocking Snag ID / Other Reason", "blocking_snag"),
    ("SIT", "sit"),
    ("Planned Execution Sequence", "planned_execution_sequence"),
    ("Critical TC Mapping", "is_critical"),
    ("Priority", "priority"),
    ("Severity", "severity"),
    ("BDD Scenario", "bdd_scenario"),
    ("Approval Status", "approval_status"),
    ("Requirement ID", "requirement_display_id"),
    ("Requirement Title", "requirement_title"),
    ("Scenario ID", "scenario_display_id"),
    ("Scenario Title", "scenario_title"),
    ("Test Phase", "test_phase"),
    ("Product Group", "product_group"),
    ("External TC ID", "external_tc_id"),
    ("External TC URL", "external_tc_url"),
    ("Created At", "created_at"),
)

TEST_CASE_TEMPLATE_HEADERS = [header for header, _ in TEST_CASE_TEMPLATE_COLUMNS]

TEST_CASE_TEMPLATE_HEADER_ALIASES = {
    header.casefold(): field for header, field in TEST_CASE_TEMPLATE_COLUMNS
}
TEST_CASE_TEMPLATE_HEADER_ALIASES.update({
    "prerequisites": "preconditions",
    "blocking snag id/other reason": "blocking_snag",
    "planned exec sequence": "planned_execution_sequence",
})
