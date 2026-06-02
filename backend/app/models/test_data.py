from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TestData(TimestampMixin, Base):
    """Reusable test datasets from Test Data Agent (Agent 6)."""
    __tablename__ = "test_data"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    test_case_id: Mapped[int | None] = mapped_column(ForeignKey("test_cases.id"), nullable=True, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    data_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    valid_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    invalid_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    boundary_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="active")
    agent_run_id: Mapped[int | None] = mapped_column(ForeignKey("agent_runs.id"), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    test_case: Mapped["TestCase | None"] = relationship("TestCase", back_populates="test_data_sets")
