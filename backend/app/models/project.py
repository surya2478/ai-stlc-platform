from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="active", nullable=False)
    # status: active | archived | completed
    ppm_id: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    project_manager_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    business_pm_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    domain: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)

    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    owner: Mapped["User"] = relationship("User", back_populates="projects", foreign_keys=[owner_id])
    jira_connections: Mapped[list["JiraConnection"]] = relationship("JiraConnection", back_populates="project")
    documents: Mapped[list["UploadedDocument"]] = relationship("UploadedDocument", back_populates="project")
    requirements: Mapped[list["Requirement"]] = relationship("Requirement", back_populates="project")
    test_plans: Mapped[list["TestPlan"]] = relationship("TestPlan", back_populates="project")
    test_scenarios: Mapped[list["TestScenario"]] = relationship("TestScenario", back_populates="project")
    test_cases: Mapped[list["TestCase"]] = relationship("TestCase", back_populates="project")
    automation_scripts: Mapped[list["AutomationScript"]] = relationship("AutomationScript", back_populates="project")
    execution_runs: Mapped[list["ExecutionRun"]] = relationship("ExecutionRun", back_populates="project")
    defect_drafts: Mapped[list["DefectDraft"]] = relationship("DefectDraft", back_populates="project")
    reports: Mapped[list["Report"]] = relationship("Report", back_populates="project")
    agent_runs: Mapped[list["AgentRun"]] = relationship("AgentRun", back_populates="project")
    memberships: Mapped[list["ProjectMembership"]] = relationship("ProjectMembership", back_populates="project")
    llm_settings: Mapped[list["ProjectLLMSetting"]] = relationship("ProjectLLMSetting", back_populates="project")
    setting_audit_logs: Mapped[list["ProjectSettingAuditLog"]] = relationship(
        "ProjectSettingAuditLog",
        back_populates="project",
    )
