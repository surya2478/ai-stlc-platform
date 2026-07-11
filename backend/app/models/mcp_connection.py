from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

CONNECTION_TYPES = ("browser", "api", "db", "kafka", "application", "custom")
TRANSPORTS = ("stdio", "http")
ACCESS_MODES = ("read_only", "read_write")
CONNECTION_STATUSES = ("connected", "not_configured", "error")


class MCPConnection(TimestampMixin, Base):
    """Registered external MCP server for Playwright AI Studio (v1: registry
    + health checks only — agents do not call these during runs yet; the
    built-in Playwright Browser MCP remains natively wired into the planner).

    Credentials/env vars are stored Fernet-encrypted (`env_encrypted`, same
    pattern as JiraConnection.jira_api_token_encrypted) and never returned
    by the API. stdio commands are allowlisted at the service layer — an
    admin can register `npx`/`uvx`-style launchers, not arbitrary binaries.
    """

    __tablename__ = "mcp_connections"
    __table_args__ = (
        CheckConstraint(
            "connection_type IN ('" + "','".join(CONNECTION_TYPES) + "')",
            name="ck_mcp_connections_type",
        ),
        CheckConstraint(
            "transport IN ('" + "','".join(TRANSPORTS) + "')",
            name="ck_mcp_connections_transport",
        ),
        CheckConstraint(
            "access_mode IN ('" + "','".join(ACCESS_MODES) + "')",
            name="ck_mcp_connections_access_mode",
        ),
        CheckConstraint(
            "status IN ('" + "','".join(CONNECTION_STATUSES) + "')",
            name="ck_mcp_connections_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    connection_type: Mapped[str] = mapped_column(String(30), nullable=False, default="custom")
    transport: Mapped[str] = mapped_column(String(10), nullable=False, default="stdio")
    # Human-readable target label shown in the UI table (e.g. "Order API SIT").
    target: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # stdio transport: executable + args (executable allowlisted in service).
    command: Mapped[str | None] = mapped_column(String(200), nullable=True)
    args: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # http transport: server URL.
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Encrypted JSON object of env vars (stdio) / headers (http) — secrets live
    # only here, never in `args` or `url`.
    env_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    access_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="read_only")
    # Subset of ["planner", "generator", "execution", "healer"] — which Studio
    # agents this connection is offered to (informational in v1).
    available_to: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="not_configured")
    tool_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # The seeded "Playwright Browser MCP" row (one per project) — not
    # editable/deletable; its health check probes the bundled @playwright/mcp
    # runtime instead of a user-supplied server.
    is_builtin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    project: Mapped["Project"] = relationship("Project")
