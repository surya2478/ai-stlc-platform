from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class ProjectLLMSetting(TimestampMixin, Base):
    __tablename__ = "project_llm_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    provider_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider_key: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_fallback: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fallback_priority: Mapped[int | None] = mapped_column(Integer, nullable=True)
    temperature: Mapped[float] = mapped_column(Float, nullable=False, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=4000)
    timeout_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=120)
    module_scope: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    config_status: Mapped[str] = mapped_column(String(50), nullable=False, default="disabled")
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    updated_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    project: Mapped["Project"] = relationship("Project", back_populates="llm_settings")


class ProjectSettingAuditLog(Base):
    __tablename__ = "project_setting_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    setting_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    old_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    new_value: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    changed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    source: Mapped[str] = mapped_column(String(80), nullable=False, default="ui")
    change_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project", back_populates="setting_audit_logs")


Index(
    "uq_project_llm_provider",
    ProjectLLMSetting.project_id,
    ProjectLLMSetting.provider_key,
    unique=True,
)
Index(
    "uq_project_primary_llm",
    ProjectLLMSetting.project_id,
    unique=True,
    postgresql_where=ProjectLLMSetting.is_primary.is_(True),
)
Index(
    "uq_project_fallback_priority",
    ProjectLLMSetting.project_id,
    ProjectLLMSetting.fallback_priority,
    unique=True,
    postgresql_where=ProjectLLMSetting.is_fallback.is_(True),
)
