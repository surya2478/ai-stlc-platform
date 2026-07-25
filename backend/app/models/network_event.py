"""UI-017 API and Network Explorer — Phase 1.

Structured, queryable request/response rows parsed from the masked
`network_log` text artifacts `capture_service._capture_optional_evidence`
already writes per `DiscoveryAction` (see `app.models.discovery_session`).
That capture is a raw call to the Playwright MCP `browser_network_requests`
tool — one line per request in the form `[METHOD] url => [status] statusText`
— never headers, bodies or timing (the MCP tool doesn't report them, so this
schema never invents those fields). `network_event_service.build_or_rebuild`
walks those already-masked files and extracts exactly what the line actually
contains; anything it can't confidently parse is kept with
`parse_state="unparsed"` and its (already masked) raw text, never guessed.

Mirrors `application_model.py`'s rebuild-in-place + residual-activity-log
pattern: `build_or_rebuild` clears and re-derives this session's events on
every call (idempotent), and `NetworkEventActivity` covers review actions
(ignore/note) the same way `ApplicationModelActivity` covers node/gap edits.
"""
from __future__ import annotations

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

NETWORK_EVENT_PARSE_STATES = ("parsed", "unparsed")
NETWORK_EVENT_REVIEW_STATES = ("unreviewed", "reviewed", "ignored")


class NetworkEvent(TimestampMixin, Base):
    """One parsed request line from a session's captured network-log text."""

    __tablename__ = "network_events"
    __table_args__ = (
        CheckConstraint(
            "parse_state IN ('" + "','".join(NETWORK_EVENT_PARSE_STATES) + "')", name="ck_network_events_parse_state"
        ),
        CheckConstraint(
            "review_state IN ('" + "','".join(NETWORK_EVENT_REVIEW_STATES) + "')", name="ck_network_events_review_state"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    capture_id: Mapped[int] = mapped_column(ForeignKey("discovery_captures.id", ondelete="CASCADE"), nullable=False, index=True)
    # The action the owning capture was taken around — gives the real
    # screen/test-step correlation (DiscoveryAction.target_screen_ref /
    # test_step_ref) without denormalizing those fields onto this row.
    action_id: Mapped[int | None] = mapped_column(ForeignKey("discovery_actions.id", ondelete="SET NULL"), nullable=True, index=True)

    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    parse_state: Mapped[str] = mapped_column(String(20), nullable=False, default="unparsed", server_default="unparsed")

    method: Mapped[str | None] = mapped_column(String(10), nullable=True, index=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    host: Mapped[str | None] = mapped_column(String(300), nullable=True, index=True)
    path: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_external: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status_code: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    status_text: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Already masked by `mask_snapshot_text` before this row is derived —
    # this column only ever holds what capture_service already wrote to disk.
    raw_line: Mapped[str] = mapped_column(Text, nullable=False)

    review_state: Mapped[str] = mapped_column(String(20), nullable=False, default="unreviewed", server_default="unreviewed")
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped["DiscoverySession"] = relationship("DiscoverySession")
    action: Mapped["DiscoveryAction | None"] = relationship("DiscoveryAction")


class NetworkEventActivity(TimestampMixin, Base):
    """Audit log for review actions on network events (build/rebuild, mark
    ignored/reviewed, export) — same rationale as `ApplicationModelActivity`.
    """

    __tablename__ = "network_event_activity"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("discovery_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    event_id: Mapped[int | None] = mapped_column(ForeignKey("network_events.id", ondelete="SET NULL"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
