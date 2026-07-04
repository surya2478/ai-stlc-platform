from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class TestSuite(TimestampMixin, Base):
    """A named tag/grouping for test cases within a project (e.g.
    "Regression Suite - Release 4.2", "Login Smoke Suite"). Each test case
    points at at most one suite via `TestCase.test_suite_id` — the same
    single-value metadata pattern as Test Environment / Telecom Domain.
    """
    __tablename__ = "test_suites"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Same taxonomy as Requirement.test_phase — SIT | QA | UAT | Regression | Production Smoke Test
    environment: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    # status: active | archived

    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    project: Mapped["Project"] = relationship("Project")
