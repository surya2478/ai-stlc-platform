"""Assertion verdicts must record how they were reached.

The suite orchestrator marks every assertion on an item as passed when the
runner reports a green test. The inference is sound — Playwright fails the test
if any web-first assertion fails — but the stored row used to be
indistinguishable from one an adapter had evaluated individually, so the
evidence claimed a per-assertion evaluation that never happened.
"""
from __future__ import annotations

import asyncio

from app.models.execution_command_center import (
    ASSERTION_EVALUATION_SOURCES,
    ExecutionRunAssertion,
)
from app.services.execution_command_center import orchestrator


class _FakeScalars:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return _FakeScalars(self._rows)


class _FakeSession:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeResult(self._rows)


class _FakeItem:
    id = 1


def test_inferred_pass_is_labelled_as_inferred():
    rows = [ExecutionRunAssertion(), ExecutionRunAssertion()]
    asyncio.run(orchestrator._mark_assertions_passed(_FakeSession(rows), _FakeItem()))

    for row in rows:
        assert row.passed is True
        # Not "reported" — the runner never attributed the result to this
        # specific assertion.
        assert row.evaluation_source == "runner_verdict"
        assert row.evaluated_at is not None


def test_runner_verdict_is_part_of_the_declared_vocabulary():
    """The value written has to satisfy the check constraint migration 053
    installs, or every suite run would fail at commit."""
    assert "runner_verdict" in ASSERTION_EVALUATION_SOURCES


def test_unevaluated_assertion_claims_no_evaluation_method():
    """The pairing constraint is (passed IS NULL) = (evaluation_source IS NULL);
    a freshly seeded row must satisfy it."""
    row = ExecutionRunAssertion()
    assert row.passed is None
    assert row.evaluation_source is None
