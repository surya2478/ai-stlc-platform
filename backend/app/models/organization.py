"""
Organization model — top-level tenant boundary.

Every Project belongs to exactly one Organization.  Users belong to an
Organization and can only access Projects within that org.  This provides
enterprise multi-tenant data isolation above the existing project-scoped RBAC.
"""
from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Organization(TimestampMixin, Base):
    """Top-level tenant for enterprise multi-tenancy."""
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Org-level settings / metadata
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # e.g. {"sso_provider": "okta", "default_llm_provider": "openai", "max_projects": 50}

    # Relationships
    users: Mapped[list["User"]] = relationship("User", back_populates="organization")
    projects: Mapped[list["Project"]] = relationship("Project", back_populates="organization")
