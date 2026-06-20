from __future__ import annotations

NORMALIZED_STATUSES = {
    "passed",
    "failed",
    "blocked",
    "skipped",
    "not_run",
    "in_progress",
    "deferred",
    "error",
    "pending",
}

STATUS_ALIASES = {
    "SUCCESS": "passed",
    "SUCCEEDED": "passed",
    "PASS": "passed",
    "PASSED": "passed",
    "OK": "passed",
    "FAILED": "failed",
    "FAIL": "failed",
    "FAILURE": "failed",
    "BLOCKED": "blocked",
    "SKIPPED": "skipped",
    "SKIP": "skipped",
    "NOT_EXECUTED": "not_run",
    "NOT RUN": "not_run",
    "NOT_RUN": "not_run",
    "RUNNING": "in_progress",
    "IN_PROGRESS": "in_progress",
    "IN PROGRESS": "in_progress",
    "DEFERRED": "deferred",
    "BROKEN": "error",
    "ABORTED": "error",
    "ERROR": "error",
    "TIMEOUT": "error",
    "PENDING": "pending",
    "QUEUED": "pending",
}


def normalize_status(status: str | None) -> str:
    if not status:
        return "pending"
    clean = str(status).strip()
    lowered = clean.lower()
    if lowered in NORMALIZED_STATUSES:
        return lowered
    return STATUS_ALIASES.get(clean.upper(), "error")
