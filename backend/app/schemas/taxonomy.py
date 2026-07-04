"""Pydantic schemas for the telecom QA taxonomy master data."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── Constants ────────────────────────────────────────────────────────────────

TaxonomyStatus = Literal["active", "draft", "retired"]

TaxonomyEntity = Literal[
    "qa_domain",
    "product_group",
    "product",
    "system",
    "sub_request_type",
]

RelationType = Literal[
    "system_supports_product",       # system → product
    "subrequest_for_product",        # sub_request_type → product
    "subrequest_for_system",         # sub_request_type → system
]

# Mapping enforced at the service layer to keep edges meaningful
RELATION_ENDPOINTS: dict[str, tuple[TaxonomyEntity, TaxonomyEntity]] = {
    "system_supports_product": ("system", "product"),
    "subrequest_for_product": ("sub_request_type", "product"),
    "subrequest_for_system": ("sub_request_type", "system"),
}


# ── Shared validators ────────────────────────────────────────────────────────


def _strip_required(value: str) -> str:
    v = (value or "").strip()
    if not v:
        raise ValueError("must not be blank")
    return v


# ── Master entity base schemas ───────────────────────────────────────────────


class _TaxonomyBase(BaseModel):
    """Fields shared by every master taxonomy entity (Read)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None = None
    name: str
    code: str
    description: str | None = None
    status: TaxonomyStatus = "active"
    owner: str | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_active: bool = True
    sort_order: int = 0
    created_at: datetime
    updated_at: datetime


class _TaxonomyCreateBase(BaseModel):
    name: str = Field(..., max_length=150)
    code: str = Field(..., max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    status: TaxonomyStatus = "active"
    owner: str | None = Field(default=None, max_length=150)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_active: bool = True
    sort_order: int = 0
    organization_id: int | None = None

    @field_validator("name", "code")
    @classmethod
    def _strip(cls, v: str) -> str:
        return _strip_required(v)

    @field_validator("code")
    @classmethod
    def _code_shape(cls, v: str) -> str:
        # Codes should be machine-friendly: letters, digits, underscore, hyphen.
        v = v.strip().upper()
        for ch in v:
            if not (ch.isalnum() or ch in "_-"):
                raise ValueError("code may only contain letters, digits, hyphen, and underscore")
        return v


class _TaxonomyUpdateBase(BaseModel):
    name: str | None = Field(default=None, max_length=150)
    code: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)
    status: TaxonomyStatus | None = None
    owner: str | None = Field(default=None, max_length=150)
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    is_active: bool | None = None
    sort_order: int | None = None

    @field_validator("name")
    @classmethod
    def _strip_name(cls, v: str | None) -> str | None:
        return None if v is None else _strip_required(v)

    @field_validator("code")
    @classmethod
    def _strip_code(cls, v: str | None) -> str | None:
        if v is None:
            return None
        v = _strip_required(v).upper()
        for ch in v:
            if not (ch.isalnum() or ch in "_-"):
                raise ValueError("code may only contain letters, digits, hyphen, and underscore")
        return v


# ── QA Domain ────────────────────────────────────────────────────────────────


class QADomainCreate(_TaxonomyCreateBase):
    pass


class QADomainUpdate(_TaxonomyUpdateBase):
    pass


class QADomainRead(_TaxonomyBase):
    pass


# ── Product Group ────────────────────────────────────────────────────────────


class ProductGroupCreate(_TaxonomyCreateBase):
    parent_id: int = Field(..., description="QA Domain id")


class ProductGroupUpdate(_TaxonomyUpdateBase):
    parent_id: int | None = None


class ProductGroupRead(_TaxonomyBase):
    parent_id: int


# ── Product ──────────────────────────────────────────────────────────────────


class ProductCreate(_TaxonomyCreateBase):
    parent_id: int = Field(..., description="Product Group id")


class ProductUpdate(_TaxonomyUpdateBase):
    parent_id: int | None = None


class ProductRead(_TaxonomyBase):
    parent_id: int


# ── System ───────────────────────────────────────────────────────────────────


class SystemCreate(_TaxonomyCreateBase):
    pass


class SystemUpdate(_TaxonomyUpdateBase):
    pass


class SystemRead(_TaxonomyBase):
    pass


# ── Sub Request Type ─────────────────────────────────────────────────────────


class SubRequestTypeCreate(_TaxonomyCreateBase):
    pass


class SubRequestTypeUpdate(_TaxonomyUpdateBase):
    pass


class SubRequestTypeRead(_TaxonomyBase):
    pass


# ── Relationships ────────────────────────────────────────────────────────────


class TaxonomyRelationshipCreate(BaseModel):
    relation_type: RelationType
    from_id: int
    to_id: int
    organization_id: int | None = None


class TaxonomyRelationshipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    organization_id: int | None = None
    relation_type: RelationType
    from_entity: TaxonomyEntity
    from_id: int
    to_entity: TaxonomyEntity
    to_id: int
    is_active: bool
    created_by: int | None = None
    created_at: datetime
    updated_at: datetime


# ── Tree / dropdown helper ───────────────────────────────────────────────────


class ProductTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    is_active: bool


class ProductGroupTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    is_active: bool
    products: list[ProductTreeNode] = Field(default_factory=list)


class QADomainTreeNode(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    code: str
    is_active: bool
    product_groups: list[ProductGroupTreeNode] = Field(default_factory=list)


class TaxonomyTree(BaseModel):
    """Bundle used by the UI's dependent dropdowns."""

    qa_domains: list[QADomainTreeNode] = Field(default_factory=list)
    systems: list[SystemRead] = Field(default_factory=list)
    sub_request_types: list[SubRequestTypeRead] = Field(default_factory=list)


__all__ = [
    "TaxonomyStatus",
    "TaxonomyEntity",
    "RelationType",
    "RELATION_ENDPOINTS",
    "QADomainCreate",
    "QADomainUpdate",
    "QADomainRead",
    "ProductGroupCreate",
    "ProductGroupUpdate",
    "ProductGroupRead",
    "ProductCreate",
    "ProductUpdate",
    "ProductRead",
    "SystemCreate",
    "SystemUpdate",
    "SystemRead",
    "SubRequestTypeCreate",
    "SubRequestTypeUpdate",
    "SubRequestTypeRead",
    "TaxonomyRelationshipCreate",
    "TaxonomyRelationshipRead",
    "ProductTreeNode",
    "ProductGroupTreeNode",
    "QADomainTreeNode",
    "TaxonomyTree",
]
