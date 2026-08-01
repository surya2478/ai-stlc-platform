"""AUT-006: a clean exit code is not a test result.

`LocalPlaywrightRunner._parse_results` used to fall back to a synthesized row
whenever the JSON reporter produced nothing usable, and that row was `pass`
when the exit code was 0. A broken config, a spec pattern that matched no test,
or a reporter that never wrote all produced a green result from a run in which
no assertion was ever evaluated.

The suite command center happened to be protected — it rejects an empty result
list — but the legacy execution path consumed the fabricated row directly.
"""
from __future__ import annotations

import json

from app.services.automation_runner.local_playwright import LocalPlaywrightRunner
from app.services.automation_runner.local_pytest import LocalPytestRunner


def _report(status: str = "passed") -> bytes:
    return json.dumps(
        {
            "suites": [
                {
                    "specs": [
                        {
                            "tests": [
                                {"results": [{"status": status, "duration": 1200}]}
                            ],
                            "title": "order flow",
                        }
                    ]
                }
            ]
        }
    ).encode("utf-8")


def test_empty_reporter_output_is_not_a_pass(tmp_path):
    rows, failure = LocalPlaywrightRunner()._parse_results(b"", tmp_path, "x.spec.ts", 0)
    assert rows == []
    assert failure is not None
    assert "no output" in failure


def test_unparseable_reporter_output_is_not_a_pass(tmp_path):
    rows, failure = LocalPlaywrightRunner()._parse_results(
        b"not json at all", tmp_path, "x.spec.ts", 0
    )
    assert rows == []
    assert "could not be parsed" in failure


def test_reporter_with_zero_tests_is_not_a_pass(tmp_path):
    """The dangerous case: playwright exits 0 because it ran nothing."""
    rows, failure = LocalPlaywrightRunner()._parse_results(
        json.dumps({"suites": []}).encode("utf-8"), tmp_path, "x.spec.ts", 0
    )
    assert rows == []
    assert "no tests" in failure


def test_parsed_results_are_returned_with_no_failure_reason(tmp_path):
    rows, failure = LocalPlaywrightRunner()._parse_results(
        _report("passed"), tmp_path, "x.spec.ts", 0
    )
    assert failure is None
    assert len(rows) == 1
    assert rows[0].status == "pass"


def test_pytest_zero_collected_tests_is_an_error_not_a_skip(tmp_path):
    """Exit code 5 means pytest collected nothing. Reporting that as "skip" read
    as a deliberately skipped test rather than a harness failure."""
    rows = LocalPytestRunner()._parse_results(
        tmp_path / "missing-report.json", tmp_path / "run.log", "test_x.py", 5
    )
    assert len(rows) == 1
    assert rows[0].status == "error"
    assert "collected 0 tests" in rows[0].error_message


def test_pytest_synthesized_row_is_flagged_as_synthesized(tmp_path):
    """Pytest's exit code genuinely means tests ran and passed, unlike
    Playwright's, so the row stands — but it must not pose as parsed detail."""
    rows = LocalPytestRunner()._parse_results(
        tmp_path / "missing-report.json", tmp_path / "run.log", "test_x.py", 0
    )
    assert rows[0].status == "pass"
    assert rows[0].raw["synthesized"] is True
