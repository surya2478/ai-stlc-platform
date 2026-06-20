from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class JiraSyncHistory(TimestampMixin, Base):
    __tablename__ = "jira_sync_history"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("jira_connections.id"), nullable=False, index=True)
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    direction: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    total_items: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    conflict_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    connection: Mapped["JiraConnection"] = relationship("JiraConnection")


class ConflictRecord(TimestampMixin, Base):
    __tablename__ = "conflict_records"
    __table_args__ = (
        UniqueConstraint("connection_id", "jira_issue_key", "status", name="uq_open_jira_conflict"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("jira_connections.id"), nullable=False, index=True)
    requirement_id: Mapped[int | None] = mapped_column(ForeignKey("requirements.id"), nullable=True, index=True)
    sync_history_id: Mapped[int | None] = mapped_column(ForeignKey("jira_sync_history.id"), nullable=True)

    jira_issue_key: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    conflict_type: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open", index=True)
    local_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    remote_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)


class WebhookEvent(TimestampMixin, Base):
    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("event_key", name="uq_webhook_events_event_key"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    connection_id: Mapped[int] = mapped_column(ForeignKey("jira_connections.id"), nullable=False, index=True)

    event_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    event_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
