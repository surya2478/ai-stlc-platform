"""The run event stream — append-only, monotonically sequenced.

This is the transport the command center polls, because the platform has no SSE
or WebSocket infrastructure (UI-046 contract Section 2.1.7). Correctness rests
entirely on the sequence number:

* It is allocated with a single `UPDATE ... RETURNING` on the run row, so two
  workers emitting concurrently cannot receive the same number. A read-then-write
  in Python would race; the unique constraint would catch it, but as a 500 rather
  than as correct behaviour.

* The client polls `?after={sequence}`. Because numbers are dense and ordered,
  reconnection after any gap replays exactly the missed events, once each —
  contract Section 14.8. A timestamp cursor could not promise that under
  parallel dispatch.

`occurred_at` is passed in by the emitter rather than defaulted in the database,
so a batched flush cannot reorder events relative to when they actually happened.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.execution import ExecutionRun
from app.models.execution_command_center import ExecutionRunEvent

# Event types the UI knows how to label (Section 7.5). Not a check constraint:
# a new event type should not need a migration, and an unknown type still
# renders with its message.
EVENT_TYPES = (
    "run_readiness_evaluated",
    "run_blocked_before_start",
    "run_queued",
    "run_started",
    "item_started",
    "step_started",
    "step_completed",
    "assertion_evaluated",
    "evidence_stored",
    "evidence_unavailable",
    "retry_started",
    "runner_warning",
    "item_result_finalized",
    "control_requested",
    "control_applied",
    "control_rejected",
    "run_paused",
    "run_resumed",
    "run_finalized",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def next_sequence(db: AsyncSession, run_id: int) -> int:
    """Atomically allocate the next sequence number for a run.

    One statement, so concurrent emitters serialize on the run row rather than
    racing between a SELECT and an UPDATE.
    """
    result = await db.execute(
        text(
            "UPDATE execution_runs SET event_sequence = event_sequence + 1 "
            "WHERE id = :run_id RETURNING event_sequence"
        ),
        {"run_id": run_id},
    )
    sequence = result.scalar_one()
    return int(sequence)


async def emit(
    db: AsyncSession,
    run_id: int,
    *,
    event_type: str,
    message: str,
    item_id: int | None = None,
    payload: dict[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> ExecutionRunEvent:
    """Append one event. Does not commit — the caller owns the transaction.

    Leaving the commit to the caller is deliberate: an event describing a state
    change must land in the same transaction as the change itself, or a crash
    between the two would leave the stream claiming something that did not
    happen.
    """
    sequence = await next_sequence(db, run_id)
    event = ExecutionRunEvent(
        execution_run_id=run_id,
        sequence=sequence,
        execution_run_item_id=item_id,
        event_type=event_type,
        message=message,
        payload=payload,
        occurred_at=occurred_at or _now(),
        created_at=_now(),
    )
    db.add(event)
    return event


async def read_after(
    db: AsyncSession, run_id: int, *, after: int = 0, limit: int = 200
) -> list[ExecutionRunEvent]:
    """Events strictly after `after`, in sequence order.

    `limit` caps one poll; the client keeps its cursor and asks again, so a long
    stall followed by a reconnect cannot produce an unbounded response.
    """
    result = await db.execute(
        select(ExecutionRunEvent)
        .where(
            ExecutionRunEvent.execution_run_id == run_id,
            ExecutionRunEvent.sequence > after,
        )
        .order_by(ExecutionRunEvent.sequence)
        .limit(limit)
    )
    return list(result.scalars().all())


async def latest_sequence(db: AsyncSession, run_id: int) -> int:
    """The run's current high-water mark, used to report poll lag."""
    result = await db.execute(
        select(ExecutionRun.event_sequence).where(ExecutionRun.id == run_id)
    )
    return int(result.scalar_one_or_none() or 0)
