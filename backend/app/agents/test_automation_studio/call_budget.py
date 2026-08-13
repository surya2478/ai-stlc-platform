"""A wall clock for a single studio LLM call.

Nothing else provides one. The provider builds its client with a scalar
`timeout`, which httpx spends per operation — "read" is the longest gap
between chunks, not the total — so a reply that trickles steadily never trips
it. And the studio's services call each agent's own `run()` rather than
`BaseAgent.run`, so the `asyncio.wait_for` in that base class never applies to
this path either.

The gap is not theoretical: one refinement call ran roughly six minutes past
its last logged activity and held a whole run open at 61% while the other
fourteen test cases sat finished. Concurrency made it worse rather than
better — a run is now only as quick as its slowest single call.

Every call site in this package already sits inside `except Exception` and
degrades sensibly, so a ceiling only has to raise something with a readable
message. That is the whole reason this raises `LLMCallTimedOut` instead of
letting `asyncio.TimeoutError` through: a bare TimeoutError stringifies to the
empty string, and those handlers put `str(exc)` straight into a toast, an
agent-run error or a skipped-item reason. The user would have read a blank.
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, TypeVar

T = TypeVar("T")


class LLMCallTimedOut(Exception):
    """One LLM call exceeded its wall-clock budget and was cancelled.

    Not a subclass of TimeoutError on purpose: `_is_retriable_llm_error` in
    the provider treats connection-level timeouts as transient and retries
    them. This one has already consumed its whole budget, and re-issuing an
    identical request buys another budget's worth of waiting.
    """


async def with_ceiling(
    awaitable: Awaitable[T],
    seconds: float | int | None,
    *,
    what: str,
    setting: str,
) -> T:
    """Await `awaitable`, cancelling it after `seconds`.

    `what` names the work in the message the user ends up reading ("this test
    case", "the coverage match"), and `setting` names the environment variable
    to raise when the work is legitimately that large.

    A falsy or non-positive budget disables the ceiling and awaits normally,
    which is what makes the settings' documented "set to 0 to disable" true.
    """
    budget = float(seconds) if seconds else 0.0
    if budget <= 0:
        return await awaitable

    try:
        return await asyncio.wait_for(awaitable, timeout=budget)
    except (asyncio.TimeoutError, TimeoutError) as exc:
        # :g rather than :.0f — a sub-second budget (the tests use one) renders
        # as "within 0s", which reads as a bug in the message rather than a
        # deliberately tight limit.
        raise LLMCallTimedOut(
            f"The model did not finish {what} within {budget:g}s and the call was cancelled. "
            f"Re-run it, or raise {setting} if the work is genuinely this large."
        ) from exc


def resolve(explicit: float | int | None, configured: Any) -> float | int | None:
    """Pick the budget for a call: an explicit argument beats configuration.

    Agents take an optional `call_timeout` so a test can pin a tight budget
    without reaching into settings. `0` is a meaningful explicit value ("no
    ceiling"), so this tests for None rather than truthiness.
    """
    return explicit if explicit is not None else configured
