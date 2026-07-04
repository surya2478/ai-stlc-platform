"""AI-assisted run detection — the one place that answers 'is this AI?'.

Post-migration 025, AI runs are ``execution_type='automation'`` with a
``metadata.ai_assisted`` flag. But some rows might have escaped backfill
(``execution_type='ai'``), and new runs also carry ``source_type='ai'`` for
provenance. Any of those signals is sufficient — the check is written that
way so callers can't accidentally drop AI runs by only looking at one field.

Kept as a standalone module with no framework imports so it can be unit-tested
without spinning up FastAPI or the DB.
"""
from __future__ import annotations

from typing import Any, Protocol


class _RunLike(Protocol):
    execution_type: str | None
    source_type: str | None
    metadata_: dict[str, Any] | None


def is_ai_assisted_run(run: _RunLike) -> bool:
    """True if the given ExecutionRun is AI-assisted.

    Recognizes three signals, in order of specificity:
        1. Legacy ``execution_type='ai'`` (pre-migration 025)
        2. ``source_type='ai'`` (provenance marker, still set today)
        3. ``metadata_.ai_assisted`` truthy (the canonical post-025 signal)

    Any one is sufficient. This is deliberately permissive so an ambiguous row
    is treated as AI (safer default for gating review workflows).
    """
    if getattr(run, "execution_type", None) == "ai":
        return True
    source = (getattr(run, "source_type", None) or "").lower()
    if source == "ai":
        return True
    meta = getattr(run, "metadata_", None) or {}
    return bool(meta.get("ai_assisted"))
