from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class LocatorMapEntry(TimestampMixin, Base):
    """Durable, per-element locator knowledge base built by the Playwright
    MCP Discovery Agent (Phase 3). One row per (application, page, element) —
    re-discovery upserts by that triple rather than accumulating duplicates,
    so `last_validated_at`/`confidence_score` always reflect the most recent
    live evidence. This is what makes locator grounding reusable across
    scripts and what the Phase 5 healing loop consults when a script starts
    failing on a stale locator.
    """
    __tablename__ = "locator_map"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="CASCADE"), nullable=True, index=True
    )

    page: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    element_name: Mapped[str] = mapped_column(String(200), nullable=False)
    business_meaning: Mapped[str | None] = mapped_column(Text, nullable=True)

    recommended_locator: Mapped[str] = mapped_column(Text, nullable=False)
    recommended_strategy: Mapped[str] = mapped_column(String(20), nullable=False)
    # recommended_strategy: role | label | placeholder | text | testid | css | xpath
    # — same vocabulary as app.services.script_compiler.locator_policy
    fallback_locator: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    last_validated_at: Mapped[object | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_by_scripts: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    project: Mapped["Project"] = relationship("Project")
    application: Mapped["ProjectApplication | None"] = relationship("ProjectApplication")
