from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ProjectApplication(TimestampMixin, Base):
    """A named application/channel under test within a project (e.g. "Web App",
    "Mobile API", "Admin Portal"), each carrying its own base URL per
    environment. Test cases tag onto one of these so AI script generation
    knows a real URL instead of inventing a placeholder domain.
    """
    __tablename__ = "project_applications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    key: Mapped[str] = mapped_column(String(80), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # {"SIT": "https://sit.example.com", "QA-Staging": "https://staging.example.com"}
    environment_urls: Mapped[dict[str, str]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Application Registry (UI-014) governance fields. Deliberately no
    # health-check, discovery-capability or AVD/device-compat columns here —
    # no backing subsystem produces that data yet; the UI renders those
    # sections as "Not configured" rather than inventing schema for them.
    application_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    aliases: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    # lifecycle_status: draft | active | deprecated | retired — kept in sync
    # with is_active by the service layer (see update_project_applications).
    lifecycle_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    business_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    technical_owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    domain: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    product_group: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    product: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    channel: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)

    project: Mapped["Project"] = relationship("Project", back_populates="applications")
    external_dependencies: Mapped[list["ProjectExternalDependency"]] = relationship(
        "ProjectExternalDependency", back_populates="application"
    )
    business_owner: Mapped["User | None"] = relationship("User", foreign_keys=[business_owner_id])
    technical_owner: Mapped["User | None"] = relationship("User", foreign_keys=[technical_owner_id])


class ProjectExternalDependency(TimestampMixin, Base):
    """A third-party service an application under test calls out to (payment
    gateway, SSO, analytics, ...). Automated tests should not hit these live —
    this is a registry passed as context to script generation so the AI mocks
    or intercepts them instead.
    """
    __tablename__ = "project_external_dependencies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True, index=True
    )
    service_name: Mapped[str] = mapped_column(String(200), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    sandbox_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # mock_strategy: intercept | sandbox | ignore
    mock_strategy: Mapped[str] = mapped_column(String(30), nullable=False, default="intercept")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    project: Mapped["Project"] = relationship("Project")
    application: Mapped["ProjectApplication | None"] = relationship(
        "ProjectApplication", back_populates="external_dependencies"
    )


Index(
    "uq_project_application_key",
    ProjectApplication.project_id,
    ProjectApplication.key,
    unique=True,
)
Index(
    "uq_project_application_default",
    ProjectApplication.project_id,
    unique=True,
    postgresql_where=ProjectApplication.is_default.is_(True),
)
