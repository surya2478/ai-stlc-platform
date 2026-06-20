from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="qa_engineer", nullable=False)
    # roles: admin | qa_engineer | qa_lead | viewer
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Relationships
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="owner", lazy="select", foreign_keys="[Project.owner_id]")
    approval_actions: Mapped[list["ApprovalAction"]] = relationship("ApprovalAction", back_populates="user", lazy="select")
    project_memberships: Mapped[list["ProjectMembership"]] = relationship(
        "ProjectMembership",
        back_populates="user",
        lazy="select",
    )
