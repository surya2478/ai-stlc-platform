"""Section 12 — resume-state classification.

Deliberately conservative: with no live browser process surviving between
Celery tasks (each pause fully closes the MCPSession per the plan's
pause/resume design), there is no live signal to diff against except what
was persisted at the last checkpoint. Anything this module cannot verify
from persisted state, it reports UNKNOWN rather than guessing — the caller
is required to offer only backend-approved recovery options (Section 12),
never to silently resume.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.models.discovery_session import DiscoveryCheckpoint, DiscoverySession

RESUME_STATES = ("UNCHANGED", "NAVIGATION_CHANGED", "SESSION_EXPIRED", "DATA_CHANGED", "APPLICATION_RESTARTED", "UNKNOWN")

RECOVERY_OPTIONS_BY_STATE: dict[str, tuple[str, ...]] = {
    "UNCHANGED": ("continue", "restore_checkpoint", "stop_and_save"),
    "NAVIGATION_CHANGED": ("remap", "restore_checkpoint", "restart_step", "stop_and_save"),
    "SESSION_EXPIRED": ("restore_checkpoint", "restart_step", "stop_and_save"),
    "DATA_CHANGED": ("remap", "restart_step", "stop_and_save"),
    "APPLICATION_RESTARTED": ("restore_checkpoint", "restart_step", "stop_and_save"),
    "UNKNOWN": ("restore_checkpoint", "restart_step", "stop_and_save"),
}

# Beyond this, a paused session's checkpoint is treated as stale enough that
# the underlying environment could plausibly have changed without this
# process observing it — conservative, not a measured SLA.
_STALE_AFTER_SECONDS = 30 * 60


@dataclass
class ResumeValidation:
    classification: str
    detail: str
    allowed_recovery_options: tuple[str, ...]


def classify_resume_state(session: DiscoverySession, checkpoint: DiscoveryCheckpoint | None) -> ResumeValidation:
    if checkpoint is None:
        return ResumeValidation(
            "UNKNOWN", "No checkpoint recorded for this session — nothing to safely resume from.",
            RECOVERY_OPTIONS_BY_STATE["UNKNOWN"],
        )
    if not checkpoint.resumable:
        return ResumeValidation(
            "SESSION_EXPIRED", "The last checkpoint was marked non-resumable (e.g. an emergency stop).",
            RECOVERY_OPTIONS_BY_STATE["SESSION_EXPIRED"],
        )

    reference = checkpoint.expires_at or checkpoint.created_at
    if reference is not None:
        now = datetime.now(reference.tzinfo or timezone.utc)
        age_seconds = (now - reference).total_seconds()
        if checkpoint.expires_at is not None and now >= checkpoint.expires_at:
            return ResumeValidation(
                "SESSION_EXPIRED", "The checkpoint's expiry has passed.", RECOVERY_OPTIONS_BY_STATE["SESSION_EXPIRED"],
            )
        if age_seconds > _STALE_AFTER_SECONDS:
            return ResumeValidation(
                "UNKNOWN",
                f"Checkpoint is {int(age_seconds // 60)} minutes old — application state cannot be confirmed unchanged.",
                RECOVERY_OPTIONS_BY_STATE["UNKNOWN"],
            )

    return ResumeValidation(
        "UNCHANGED", "Checkpoint is recent and was not marked expired.", RECOVERY_OPTIONS_BY_STATE["UNCHANGED"],
    )
