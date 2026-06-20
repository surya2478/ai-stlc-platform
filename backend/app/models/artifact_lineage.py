from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.base import TimestampMixin


class ArtifactLineage(TimestampMixin, Base):
    """Append-only parent/child lineage between STLC artifacts."""
    __tablename__ = "artifact_lineage"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("agent_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )

    parent_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    parent_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    child_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    child_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    relationship_type: Mapped[str] = mapped_column(String(100), nullable=False, default="generated_from")
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="agent")
    correlation_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
