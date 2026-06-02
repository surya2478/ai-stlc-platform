from sqlalchemy import ForeignKey, String, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class JiraConnection(TimestampMixin, Base):
    __tablename__ = "jira_connections"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    jira_base_url: Mapped[str] = mapped_column(String(500), nullable=False)
    jira_email: Mapped[str] = mapped_column(String(255), nullable=False)
    # API token stored encrypted — never plaintext
    jira_api_token_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    jira_project_key: Mapped[str] = mapped_column(String(50), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_sync_at: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="connected")
    # status: connected | error | disconnected

    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="jira_connections")
