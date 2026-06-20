from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class AutomationTestMapping(TimestampMixin, Base):
    """Maps an internal STLC test case to an external automation tool test case."""

    __tablename__ = "automation_test_mappings"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "external_tool_name",
            "external_test_case_id",
            name="uq_auto_mapping_project_tool_external_tc",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    external_tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    external_project_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_suite_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_test_case_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_script_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    automation_status: Mapped[str] = mapped_column(String(50), default="ready_for_automation", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_synced_at: Mapped[DateTime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped["Project"] = relationship("Project")
    test_case: Mapped["TestCase"] = relationship("TestCase", back_populates="automation_mappings")
