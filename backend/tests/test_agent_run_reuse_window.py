"""Source-analysis runs stop being reusable once they are no longer fresh.

Found live: re-running "Analyze Portal URL" on a URL already analysed the day
before showed "Portal requirements generated successfully" and produced nothing.
The idempotency key is derived from project, user, agent, prompt version and
input — none of which change when the same URL is submitted again — so the first
completed run answered that input permanently. Nothing was queued, the frontend
polled the day-old run, saw "completed", and reported success.

The same input naming the same *source* is not the same computation: the page
may have changed, and the analysis itself may have improved. Reuse here is a
double-click guard, not a permanent verdict.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import anyio
import pytest

from app.services.agent_dispatch_service import (
    _SOURCE_ANALYSIS_AGENTS,
    _SOURCE_ANALYSIS_REUSE_WINDOW,
    _completed_run_is_reusable,
    _within_reuse_window,
)


class _Run:
    def __init__(self, age: timedelta | None = None, naive: bool = False):
        if age is None:
            self.updated_at = None
            self.created_at = None
            return
        stamp = datetime.now(timezone.utc) - age
        self.updated_at = stamp.replace(tzinfo=None) if naive else stamp
        self.created_at = self.updated_at


def _reusable(agent_name: str, run) -> bool:
    return anyio.run(lambda: _completed_run_is_reusable(None, run, agent_name))


# ── The window ──────────────────────────────────────────────────────────────


def test_a_run_from_seconds_ago_is_reused():
    """The case reuse exists for: an impatient second click."""
    assert _within_reuse_window(_Run(timedelta(seconds=5)))


def test_a_run_from_yesterday_is_not_reused():
    """The reported bug, exactly: a day-old run answering today's request."""
    assert not _within_reuse_window(_Run(timedelta(days=1)))


def test_the_boundary_falls_on_the_configured_window():
    assert _within_reuse_window(_Run(_SOURCE_ANALYSIS_REUSE_WINDOW - timedelta(seconds=5)))
    assert not _within_reuse_window(_Run(_SOURCE_ANALYSIS_REUSE_WINDOW + timedelta(seconds=5)))


def test_a_run_with_no_timestamp_is_not_reused():
    """Unknown age must fall back to re-running, not to reuse — a wrong reuse is
    silent, a wrong re-run merely costs time."""
    assert not _within_reuse_window(_Run(None))


def test_naive_timestamps_do_not_raise():
    """Guards the comparison itself: a naive datetime against an aware `now`
    raises TypeError, which would surface as a 500 on a normal re-run."""
    assert _within_reuse_window(_Run(timedelta(seconds=5), naive=True))
    assert not _within_reuse_window(_Run(timedelta(days=1), naive=True))


# ── Which agents it applies to ──────────────────────────────────────────────


@pytest.mark.parametrize("agent_name", sorted(_SOURCE_ANALYSIS_AGENTS))
def test_stale_source_analysis_runs_are_re_queued(agent_name):
    assert _reusable(agent_name, _Run(timedelta(days=1))) is False
    assert _reusable(agent_name, _Run(timedelta(seconds=5))) is True


def test_url_and_image_analysis_are_both_covered():
    """Both feed requirement generation from a source that can change, and both
    had the same permanent-reuse behaviour."""
    assert "url_analysis" in _SOURCE_ANALYSIS_AGENTS
    assert "ui_image_analysis" in _SOURCE_ANALYSIS_AGENTS


def test_agents_outside_the_set_keep_their_own_rules():
    """Content-derived agents are unaffected: the same input really is the same
    computation, so permanent reuse remains correct for them."""
    assert _reusable("requirement_quality", _Run(timedelta(days=30))) is True
