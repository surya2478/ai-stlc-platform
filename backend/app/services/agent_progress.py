"""A channel for an agent to report what it is actually doing.

Agents are invoked through `AGENT_REGISTRY`, whose functions take only
`input_data` and have no access to the AgentRun row or the session. So the
only progress the UI ever saw came from the task wrapper around them: 10
"Worker started", 30 "Agent execution started", 90 "Persisting agent result".
A wave of six script generations sat at 30% for five and a half minutes with
the message "Agent execution started" — true, and useless.

A ContextVar rather than a new parameter on every agent: the same pattern
`app.llm.provider` already uses for per-run LLM routes, and it means an agent
that has nothing useful to report needs no change at all.

Agents report progress through their OWN work as 0-100. The reporter installed
by the task wrapper scales that into the band between "execution started" and
"persisting result", so the wrapper's existing milestones keep their meaning.
"""
from __future__ import annotations

import logging
from contextvars import ContextVar, Token
from typing import Awaitable, Callable

logger = logging.getLogger(__name__)

ProgressReporter = Callable[[int, str], Awaitable[None]]

_reporter: ContextVar[ProgressReporter | None] = ContextVar("agent_progress_reporter", default=None)


def set_progress_reporter(reporter: ProgressReporter | None) -> Token:
    return _reporter.set(reporter)


def reset_progress_reporter(token: Token) -> None:
    _reporter.reset(token)


async def report_progress(percent: int, message: str) -> None:
    """Report how far through its own work the running agent is.

    Never raises: progress is commentary, and an agent must not fail because
    its status update could not be written.
    """
    reporter = _reporter.get()
    if reporter is None:
        return
    try:
        await reporter(max(0, min(100, int(percent))), message)
    except Exception:  # pragma: no cover - defensive
        logger.warning("agent progress report failed", exc_info=True)
