"""DB-safe human-readable display ID helpers."""
from __future__ import annotations

import uuid


def temporary_id(prefix: str) -> str:
    return f"{prefix}-TMP-{uuid.uuid4().hex}"


def display_id(prefix: str, row_id: int) -> str:
    return f"{prefix}-{row_id:04d}"
