"""Business logic for telecom QA taxonomy master data."""
from __future__ import annotations

from typing import Sequence, Type, TypeVar

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.taxonomy import (
    BusinessProcess,
    Environment,
    Product,
    ProductGroup,
    QADomain,
    SubRequestType,
    System,
    TaxonomyRelationship,
    TestCaseComplexity,
    TestCaseType,
)
from app.models.user import User
from app.schemas.taxonomy import (
    RELATION_ENDPOINTS,
    BusinessProcessCreate,
    BusinessProcessUpdate,
    EnvironmentCreate,
    EnvironmentUpdate,
    ProductCreate,
    ProductGroupCreate,
    ProductGroupUpdate,
    ProductUpdate,
    QADomainCreate,
    QADomainUpdate,
    SubRequestTypeCreate,
    SubRequestTypeUpdate,
    SystemCreate,
    SystemUpdate,
    TaxonomyEntity,
    TaxonomyRelationshipCreate,
    TaxonomyTree,
    TestCaseComplexityCreate,
    TestCaseComplexityUpdate,
    TestCaseTypeCreate,
    TestCaseTypeUpdate,
)
from app.services.rbac_service import is_platform_admin


# ── Admin gate ───────────────────────────────────────────────────────────────

def require_taxonomy_admin(user: User) -> None:
    """Phase 1: only platform admins can mutate taxonomy.

    A finer-grained ``MANAGE_TAXONOMY`` permission can be added later if the
    org-level RBAC model demands it.
    """
    if not is_platform_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can modify the taxonomy.",
        )


# ── Generic helpers ──────────────────────────────────────────────────────────

_MODEL_BY_ENTITY: dict[TaxonomyEntity, type] = {
    "qa_domain": QADomain,
    "product_group": ProductGroup,
    "product": Product,
    "system": System,
    "sub_request_type": SubRequestType,
    "business_process": BusinessProcess,
}

T = TypeVar("T")


async def _get_or_404(db: AsyncSession, model: type[T], entity_id: int, label: str) -> T:
    obj = await db.get(model, entity_id)
    if obj is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{label} not found")
    return obj


def _apply_updates(obj: object, updates: dict) -> None:
    for k, v in updates.items():
        setattr(obj, k, v)


async def _flush_with_dupe_check(db: AsyncSession, *, code: str) -> None:
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"A taxonomy entry with code '{code}' already exists for this organization.",
        ) from exc


# ── QA Domain ────────────────────────────────────────────────────────────────


class QADomainService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, *, active_only: bool = False) -> Sequence[QADomain]:
        stmt = select(QADomain).order_by(QADomain.sort_order, QADomain.name)
        if active_only:
            stmt = stmt.where(QADomain.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get(self, qa_id: int) -> QADomain:
        return await _get_or_404(self.db, QADomain, qa_id, "QA Domain")

    async def create(self, data: QADomainCreate, user: User) -> QADomain:
        require_taxonomy_admin(user)
        obj = QADomain(**data.model_dump())
        self.db.add(obj)
        await _flush_with_dupe_check(self.db, code=data.code)
        return obj

    async def update(self, qa_id: int, data: QADomainUpdate, user: User) -> QADomain:
        require_taxonomy_admin(user)
        obj = await self.get(qa_id)
        _apply_updates(obj, data.model_dump(exclude_unset=True))
        await _flush_with_dupe_check(self.db, code=obj.code)
        return obj

    async def deactivate(self, qa_id: int, user: User) -> QADomain:
        require_taxonomy_admin(user)
        obj = await self.get(qa_id)
        obj.is_active = False
        obj.status = "retired"
        await self.db.flush()
        return obj


# ── Product Group ────────────────────────────────────────────────────────────


class ProductGroupService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, *, parent_id: int | None = None, active_only: bool = False) -> Sequence[ProductGroup]:
        stmt = select(ProductGroup).order_by(ProductGroup.sort_order, ProductGroup.name)
        if parent_id is not None:
            stmt = stmt.where(ProductGroup.parent_id == parent_id)
        if active_only:
            stmt = stmt.where(ProductGroup.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get(self, pg_id: int) -> ProductGroup:
        return await _get_or_404(self.db, ProductGroup, pg_id, "Product Group")

    async def create(self, data: ProductGroupCreate, user: User) -> ProductGroup:
        require_taxonomy_admin(user)
        # A domain is optional (migration 059), but naming one that does not
        # exist is still an error rather than a silently dropped field.
        if data.parent_id is not None:
            await _get_or_404(self.db, QADomain, data.parent_id, "QA Domain")
        obj = ProductGroup(**data.model_dump())
        self.db.add(obj)
        await _flush_with_dupe_check(self.db, code=data.code)
        return obj

    async def update(self, pg_id: int, data: ProductGroupUpdate, user: User) -> ProductGroup:
        require_taxonomy_admin(user)
        obj = await self.get(pg_id)
        updates = data.model_dump(exclude_unset=True)
        if "parent_id" in updates and updates["parent_id"] is not None:
            await _get_or_404(self.db, QADomain, updates["parent_id"], "QA Domain")
        _apply_updates(obj, updates)
        await _flush_with_dupe_check(self.db, code=obj.code)
        return obj

    async def deactivate(self, pg_id: int, user: User) -> ProductGroup:
        require_taxonomy_admin(user)
        obj = await self.get(pg_id)
        obj.is_active = False
        obj.status = "retired"
        await self.db.flush()
        return obj


# ── Product ──────────────────────────────────────────────────────────────────


class ProductService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, *, parent_id: int | None = None, active_only: bool = False) -> Sequence[Product]:
        stmt = select(Product).order_by(Product.sort_order, Product.name)
        if parent_id is not None:
            stmt = stmt.where(Product.parent_id == parent_id)
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get(self, product_id: int) -> Product:
        return await _get_or_404(self.db, Product, product_id, "Product")

    async def create(self, data: ProductCreate, user: User) -> Product:
        require_taxonomy_admin(user)
        await _get_or_404(self.db, ProductGroup, data.parent_id, "Product Group")
        obj = Product(**data.model_dump())
        self.db.add(obj)
        await _flush_with_dupe_check(self.db, code=data.code)
        return obj

    async def update(self, product_id: int, data: ProductUpdate, user: User) -> Product:
        require_taxonomy_admin(user)
        obj = await self.get(product_id)
        updates = data.model_dump(exclude_unset=True)
        if "parent_id" in updates and updates["parent_id"] is not None:
            await _get_or_404(self.db, ProductGroup, updates["parent_id"], "Product Group")
        _apply_updates(obj, updates)
        await _flush_with_dupe_check(self.db, code=obj.code)
        return obj

    async def deactivate(self, product_id: int, user: User) -> Product:
        require_taxonomy_admin(user)
        obj = await self.get(product_id)
        obj.is_active = False
        obj.status = "retired"
        await self.db.flush()
        return obj


# ── System / SubRequestType (flat, no parent) ────────────────────────────────


class _FlatTaxonomyService:
    model: type
    label: str

    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(self, *, active_only: bool = False) -> Sequence:
        stmt = select(self.model).order_by(self.model.sort_order, self.model.name)
        if active_only:
            stmt = stmt.where(self.model.is_active.is_(True))
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get(self, entity_id: int):
        return await _get_or_404(self.db, self.model, entity_id, self.label)

    async def _create(self, data, user: User):
        require_taxonomy_admin(user)
        obj = self.model(**data.model_dump())
        self.db.add(obj)
        await _flush_with_dupe_check(self.db, code=data.code)
        return obj

    async def _update(self, entity_id: int, data, user: User):
        require_taxonomy_admin(user)
        obj = await self.get(entity_id)
        _apply_updates(obj, data.model_dump(exclude_unset=True))
        await _flush_with_dupe_check(self.db, code=obj.code)
        return obj

    async def deactivate(self, entity_id: int, user: User):
        require_taxonomy_admin(user)
        obj = await self.get(entity_id)
        obj.is_active = False
        obj.status = "retired"
        await self.db.flush()
        return obj


class SystemService(_FlatTaxonomyService):
    model = System
    label = "System"

    async def create(self, data: SystemCreate, user: User) -> System:
        return await self._create(data, user)

    async def update(self, entity_id: int, data: SystemUpdate, user: User) -> System:
        return await self._update(entity_id, data, user)


class SubRequestTypeService(_FlatTaxonomyService):
    model = SubRequestType
    label = "Sub Request Type"

    async def create(self, data: SubRequestTypeCreate, user: User) -> SubRequestType:
        return await self._create(data, user)

    async def update(self, entity_id: int, data: SubRequestTypeUpdate, user: User) -> SubRequestType:
        return await self._update(entity_id, data, user)


class BusinessProcessService(_FlatTaxonomyService):
    model = BusinessProcess
    label = "Business Process"

    async def create(self, data: BusinessProcessCreate, user: User) -> BusinessProcess:
        return await self._create(data, user)

    async def update(self, entity_id: int, data: BusinessProcessUpdate, user: User) -> BusinessProcess:
        return await self._update(entity_id, data, user)


class TestCaseTypeService(_FlatTaxonomyService):
    model = TestCaseType
    label = "Test Case Type"

    async def create(self, data: TestCaseTypeCreate, user: User) -> TestCaseType:
        return await self._create(data, user)

    async def update(self, entity_id: int, data: TestCaseTypeUpdate, user: User) -> TestCaseType:
        return await self._update(entity_id, data, user)


class TestCaseComplexityService(_FlatTaxonomyService):
    model = TestCaseComplexity
    label = "Test Case Complexity"

    async def create(self, data: TestCaseComplexityCreate, user: User) -> TestCaseComplexity:
        return await self._create(data, user)

    async def update(self, entity_id: int, data: TestCaseComplexityUpdate, user: User) -> TestCaseComplexity:
        return await self._update(entity_id, data, user)


class EnvironmentService(_FlatTaxonomyService):
    model = Environment
    label = "Environment"

    async def create(self, data: EnvironmentCreate, user: User) -> Environment:
        return await self._create(data, user)

    async def update(self, entity_id: int, data: EnvironmentUpdate, user: User) -> Environment:
        return await self._update(entity_id, data, user)


# ── Relationships (polymorphic M:N) ──────────────────────────────────────────


class TaxonomyRelationshipService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list(
        self,
        *,
        relation_type: str | None = None,
        from_id: int | None = None,
        to_id: int | None = None,
    ) -> Sequence[TaxonomyRelationship]:
        stmt = select(TaxonomyRelationship).where(TaxonomyRelationship.is_active.is_(True))
        if relation_type is not None:
            stmt = stmt.where(TaxonomyRelationship.relation_type == relation_type)
        if from_id is not None:
            stmt = stmt.where(TaxonomyRelationship.from_id == from_id)
        if to_id is not None:
            stmt = stmt.where(TaxonomyRelationship.to_id == to_id)
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def create(self, data: TaxonomyRelationshipCreate, user: User) -> TaxonomyRelationship:
        require_taxonomy_admin(user)
        if data.relation_type not in RELATION_ENDPOINTS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported relation_type: {data.relation_type}",
            )
        from_entity, to_entity = RELATION_ENDPOINTS[data.relation_type]

        # Validate endpoints exist.
        await _get_or_404(self.db, _MODEL_BY_ENTITY[from_entity], data.from_id, from_entity)
        await _get_or_404(self.db, _MODEL_BY_ENTITY[to_entity], data.to_id, to_entity)

        obj = TaxonomyRelationship(
            organization_id=data.organization_id,
            relation_type=data.relation_type,
            from_entity=from_entity,
            from_id=data.from_id,
            to_entity=to_entity,
            to_id=data.to_id,
            created_by=user.id,
        )
        self.db.add(obj)
        try:
            await self.db.flush()
        except IntegrityError as exc:
            await self.db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Relationship already exists.",
            ) from exc
        return obj

    async def delete(self, rel_id: int, user: User) -> None:
        require_taxonomy_admin(user)
        obj = await _get_or_404(self.db, TaxonomyRelationship, rel_id, "Relationship")
        obj.is_active = False
        await self.db.flush()


# ── Tree assembly (used by dependent dropdowns) ──────────────────────────────


class TaxonomyTreeService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_tree(self, *, active_only: bool = True) -> TaxonomyTree:
        domain_stmt = (
            select(QADomain)
            .options(selectinload(QADomain.product_groups).selectinload(ProductGroup.products))
            .order_by(QADomain.sort_order, QADomain.name)
        )
        if active_only:
            domain_stmt = domain_stmt.where(QADomain.is_active.is_(True))
        domains = (await self.db.execute(domain_stmt)).scalars().all()

        sys_stmt = select(System).order_by(System.sort_order, System.name)
        srt_stmt = select(SubRequestType).order_by(SubRequestType.sort_order, SubRequestType.name)
        bp_stmt = select(BusinessProcess).order_by(BusinessProcess.sort_order, BusinessProcess.name)
        if active_only:
            sys_stmt = sys_stmt.where(System.is_active.is_(True))
            srt_stmt = srt_stmt.where(SubRequestType.is_active.is_(True))
            bp_stmt = bp_stmt.where(BusinessProcess.is_active.is_(True))

        systems = (await self.db.execute(sys_stmt)).scalars().all()
        sub_request_types = (await self.db.execute(srt_stmt)).scalars().all()
        business_processes = (await self.db.execute(bp_stmt)).scalars().all()

        tct_stmt = select(TestCaseType).order_by(TestCaseType.sort_order, TestCaseType.name)
        tcc_stmt = select(TestCaseComplexity).order_by(TestCaseComplexity.sort_order, TestCaseComplexity.name)
        env_stmt = select(Environment).order_by(Environment.sort_order, Environment.name)
        if active_only:
            tct_stmt = tct_stmt.where(TestCaseType.is_active.is_(True))
            tcc_stmt = tcc_stmt.where(TestCaseComplexity.is_active.is_(True))
            env_stmt = env_stmt.where(Environment.is_active.is_(True))

        test_case_types = (await self.db.execute(tct_stmt)).scalars().all()
        test_case_complexities = (await self.db.execute(tcc_stmt)).scalars().all()
        environments = (await self.db.execute(env_stmt)).scalars().all()

        from app.schemas.taxonomy import (
            QADomainTreeNode,
            ProductGroupTreeNode,
            ProductTreeNode,
            SystemRead,
            SubRequestTypeRead,
            BusinessProcessRead,
            TestCaseTypeRead,
            TestCaseComplexityRead,
            EnvironmentRead,
        )

        return TaxonomyTree(
            test_case_types=[TestCaseTypeRead.model_validate(t) for t in test_case_types],
            test_case_complexities=[TestCaseComplexityRead.model_validate(t) for t in test_case_complexities],
            environments=[EnvironmentRead.model_validate(e) for e in environments],
            qa_domains=[
                QADomainTreeNode(
                    id=d.id,
                    name=d.name,
                    code=d.code,
                    is_active=d.is_active,
                    product_groups=[
                        ProductGroupTreeNode(
                            id=pg.id,
                            name=pg.name,
                            code=pg.code,
                            is_active=pg.is_active,
                            products=[
                                ProductTreeNode(
                                    id=p.id,
                                    name=p.name,
                                    code=p.code,
                                    is_active=p.is_active,
                                )
                                for p in (pg.products or [])
                                if (p.is_active or not active_only)
                            ],
                        )
                        for pg in (d.product_groups or [])
                        if (pg.is_active or not active_only)
                    ],
                )
                for d in domains
            ],
            systems=[SystemRead.model_validate(s) for s in systems],
            sub_request_types=[SubRequestTypeRead.model_validate(s) for s in sub_request_types],
            business_processes=[BusinessProcessRead.model_validate(b) for b in business_processes],
        )


__all__ = [
    "QADomainService",
    "ProductGroupService",
    "ProductService",
    "SystemService",
    "SubRequestTypeService",
    "BusinessProcessService",
    "TestCaseTypeService",
    "TestCaseComplexityService",
    "EnvironmentService",
    "TaxonomyRelationshipService",
    "TaxonomyTreeService",
    "require_taxonomy_admin",
]
