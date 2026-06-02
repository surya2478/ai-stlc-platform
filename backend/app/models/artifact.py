from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


class Artifact(TimestampMixin, Base):
    """
    Binary artifacts associated with execution, reports, or agent runs.
    Examples: screenshots, videos, trace files, Allure HTML packages, exported PDFs.
    """
    __tablename__ = "artifacts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    artifact_type: Mapped[str] = mapped_column(String(100), nullable=False)
    # screenshot | video | trace | allure_report | pdf_report | excel_export | log

    entity_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # execution_result | execution_run | report | agent_run
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    mime_type: Mapped[str | None] = mapped_column(String(200), nullable=True)

    status: Mapped[str] = mapped_column(String(50), default="available")
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
