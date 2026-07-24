"""
Centrally governed master-data taxonomy for telecom QA classification.

Hierarchy:
    QA Domain → Product Group → Product
                                 ↘   ↘
                             System (M:N), Sub Request Type (M:N to Product and System)

Phase 1 (this file) only models the master tables and their parent/child links.
Inheritance into Requirements/Plans/Cases lands in later phases.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin


# ── Shared columns ────────────────────────────────────────────────────────────


class _TaxonomyCommonMixin(TimestampMixin):
    """Columns shared by every taxonomy entity.

    Declared as a mixin so each table gets its own column definitions
    (SQLAlchemy mixins are class-level templates, not shared rows).
    """

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="active", nullable=False)
    # status: active | draft | retired
    owner: Mapped[str | None] = mapped_column(String(150), nullable=True)
    effective_from: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    effective_to: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


# ── Master entities ───────────────────────────────────────────────────────────


class QADomain(_TaxonomyCommonMixin, Base):
    """Highest business or technology domain classification."""

    __tablename__ = "qa_domains"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_qa_domains_org_code"),
    )

    product_groups: Mapped[list["ProductGroup"]] = relationship(
        "ProductGroup",
        back_populates="qa_domain",
        cascade="all, delete-orphan",
    )


class ProductGroup(_TaxonomyCommonMixin, Base):
    """A product family under a QA Domain."""

    __tablename__ = "product_groups"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_product_groups_org_code"),
    )

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("qa_domains.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    qa_domain: Mapped["QADomain"] = relationship("QADomain", back_populates="product_groups")
    products: Mapped[list["Product"]] = relationship(
        "Product",
        back_populates="product_group",
        cascade="all, delete-orphan",
    )


class Product(_TaxonomyCommonMixin, Base):
    """A specific commercial or technical product under a Product Group."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_products_org_code"),
    )

    parent_id: Mapped[int] = mapped_column(
        ForeignKey("product_groups.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_group: Mapped["ProductGroup"] = relationship("ProductGroup", back_populates="products")


class System(_TaxonomyCommonMixin, Base):
    """An application/platform/service/external system under test."""

    __tablename__ = "systems"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_systems_org_code"),
    )


class SubRequestType(_TaxonomyCommonMixin, Base):
    """A specific business request, change, journey, or service operation."""

    __tablename__ = "sub_request_types"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_sub_request_types_org_code"),
    )


class TestCaseType(_TaxonomyCommonMixin, Base):
    """Controlled vocabulary for the UAT template's Test Case Type column."""

    __tablename__ = "test_case_types"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_test_case_types_org_code"),
    )


class TestCaseComplexity(_TaxonomyCommonMixin, Base):
    """Controlled vocabulary for the UAT template's Test Case Complexity column."""

    __tablename__ = "test_case_complexities"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_test_case_complexities_org_code"),
    )


class Environment(_TaxonomyCommonMixin, Base):
    """Controlled vocabulary for plan-time / execution-time Environment (SIT, QA, UAT, ...)."""

    __tablename__ = "environments"
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_environments_org_code"),
    )


# ── Many-to-many edges (system↔product, sub-request-type↔{product,system}) ───
#
# Modelled as a single polymorphic table so future M:N edges can be added
# without new migrations (sub_request_type ↔ business_flow, etc).


class TaxonomyRelationship(TimestampMixin, Base):
    """Polymorphic M:N edge between any two taxonomy entities.

    Supported `relation_type` values:
        - system_supports_product   (from_entity=system,           to_entity=product)
        - subrequest_for_product    (from_entity=sub_request_type, to_entity=product)
        - subrequest_for_system     (from_entity=sub_request_type, to_entity=system)

    `from_entity` / `to_entity` are short codes matching one of:
        qa_domain | product_group | product | system | sub_request_type
    """

    __tablename__ = "taxonomy_relationships"
    __table_args__ = (
        UniqueConstraint(
            "relation_type",
            "from_entity",
            "from_id",
            "to_entity",
            "to_id",
            name="uq_taxonomy_relationships_edge",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    organization_id: Mapped[int | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    relation_type: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    from_entity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    from_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    to_entity: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    to_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


__all__ = [
    "QADomain",
    "ProductGroup",
    "Product",
    "System",
    "SubRequestType",
    "TestCaseType",
    "TestCaseComplexity",
    "Environment",
    "TaxonomyRelationship",
]
