"""Taxonomy endpoints — centrally governed telecom QA master data.

Exposes the taxonomy tables (`app/models/taxonomy.py`) and their service
layer (`app/services/taxonomy_service.py`), previously modeled and schema'd
but never mounted to a router. Read endpoints are available to any
authenticated user (they back dropdowns across Requirements, Test Cases,
Test Planning and Execution); mutations are gated by
`taxonomy_service.require_taxonomy_admin`.
"""
from fastapi import APIRouter

from app.api.deps import CurrentUser, DBSession
from app.schemas.common import MessageResponse
from app.schemas.taxonomy import (
    EnvironmentCreate,
    EnvironmentRead,
    EnvironmentUpdate,
    ProductCreate,
    ProductGroupCreate,
    ProductGroupRead,
    ProductGroupUpdate,
    ProductRead,
    ProductUpdate,
    QADomainCreate,
    QADomainRead,
    QADomainUpdate,
    SubRequestTypeCreate,
    SubRequestTypeRead,
    SubRequestTypeUpdate,
    SystemCreate,
    SystemRead,
    SystemUpdate,
    TaxonomyRelationshipCreate,
    TaxonomyRelationshipRead,
    TaxonomyTree,
    TestCaseComplexityCreate,
    TestCaseComplexityRead,
    TestCaseComplexityUpdate,
    TestCaseTypeCreate,
    TestCaseTypeRead,
    TestCaseTypeUpdate,
)
from app.services.taxonomy_service import (
    EnvironmentService,
    ProductGroupService,
    ProductService,
    QADomainService,
    SubRequestTypeService,
    SystemService,
    TaxonomyRelationshipService,
    TaxonomyTreeService,
    TestCaseComplexityService,
    TestCaseTypeService,
)

router = APIRouter()


@router.get("/tree", response_model=TaxonomyTree)
async def get_taxonomy_tree(db: DBSession, current_user: CurrentUser, active_only: bool = True):
    return await TaxonomyTreeService(db).get_tree(active_only=active_only)


# ── QA Domains ───────────────────────────────────────────────────────────────

@router.get("/qa-domains", response_model=list[QADomainRead])
async def list_qa_domains(db: DBSession, current_user: CurrentUser, active_only: bool = False):
    return await QADomainService(db).list(active_only=active_only)


@router.post("/qa-domains", response_model=QADomainRead, status_code=201)
async def create_qa_domain(data: QADomainCreate, db: DBSession, current_user: CurrentUser):
    obj = await QADomainService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/qa-domains/{entity_id}", response_model=QADomainRead)
async def update_qa_domain(entity_id: int, data: QADomainUpdate, db: DBSession, current_user: CurrentUser):
    obj = await QADomainService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/qa-domains/{entity_id}", response_model=MessageResponse)
async def deactivate_qa_domain(entity_id: int, db: DBSession, current_user: CurrentUser):
    await QADomainService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "QA Domain deactivated"}


# ── Product Groups ───────────────────────────────────────────────────────────

@router.get("/product-groups", response_model=list[ProductGroupRead])
async def list_product_groups(
    db: DBSession, current_user: CurrentUser, parent_id: int | None = None, active_only: bool = False
):
    return await ProductGroupService(db).list(parent_id=parent_id, active_only=active_only)


@router.post("/product-groups", response_model=ProductGroupRead, status_code=201)
async def create_product_group(data: ProductGroupCreate, db: DBSession, current_user: CurrentUser):
    obj = await ProductGroupService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/product-groups/{entity_id}", response_model=ProductGroupRead)
async def update_product_group(entity_id: int, data: ProductGroupUpdate, db: DBSession, current_user: CurrentUser):
    obj = await ProductGroupService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/product-groups/{entity_id}", response_model=MessageResponse)
async def deactivate_product_group(entity_id: int, db: DBSession, current_user: CurrentUser):
    await ProductGroupService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "Product Group deactivated"}


# ── Products ─────────────────────────────────────────────────────────────────

@router.get("/products", response_model=list[ProductRead])
async def list_products(
    db: DBSession, current_user: CurrentUser, parent_id: int | None = None, active_only: bool = False
):
    return await ProductService(db).list(parent_id=parent_id, active_only=active_only)


@router.post("/products", response_model=ProductRead, status_code=201)
async def create_product(data: ProductCreate, db: DBSession, current_user: CurrentUser):
    obj = await ProductService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/products/{entity_id}", response_model=ProductRead)
async def update_product(entity_id: int, data: ProductUpdate, db: DBSession, current_user: CurrentUser):
    obj = await ProductService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/products/{entity_id}", response_model=MessageResponse)
async def deactivate_product(entity_id: int, db: DBSession, current_user: CurrentUser):
    await ProductService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "Product deactivated"}


# ── Systems (Channel) ────────────────────────────────────────────────────────

@router.get("/systems", response_model=list[SystemRead])
async def list_systems(db: DBSession, current_user: CurrentUser, active_only: bool = False):
    return await SystemService(db).list(active_only=active_only)


@router.post("/systems", response_model=SystemRead, status_code=201)
async def create_system(data: SystemCreate, db: DBSession, current_user: CurrentUser):
    obj = await SystemService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/systems/{entity_id}", response_model=SystemRead)
async def update_system(entity_id: int, data: SystemUpdate, db: DBSession, current_user: CurrentUser):
    obj = await SystemService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/systems/{entity_id}", response_model=MessageResponse)
async def deactivate_system(entity_id: int, db: DBSession, current_user: CurrentUser):
    await SystemService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "System deactivated"}


# ── Sub Request Types ────────────────────────────────────────────────────────

@router.get("/sub-request-types", response_model=list[SubRequestTypeRead])
async def list_sub_request_types(db: DBSession, current_user: CurrentUser, active_only: bool = False):
    return await SubRequestTypeService(db).list(active_only=active_only)


@router.post("/sub-request-types", response_model=SubRequestTypeRead, status_code=201)
async def create_sub_request_type(data: SubRequestTypeCreate, db: DBSession, current_user: CurrentUser):
    obj = await SubRequestTypeService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/sub-request-types/{entity_id}", response_model=SubRequestTypeRead)
async def update_sub_request_type(entity_id: int, data: SubRequestTypeUpdate, db: DBSession, current_user: CurrentUser):
    obj = await SubRequestTypeService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/sub-request-types/{entity_id}", response_model=MessageResponse)
async def deactivate_sub_request_type(entity_id: int, db: DBSession, current_user: CurrentUser):
    await SubRequestTypeService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "Sub Request Type deactivated"}


# ── Test Case Types ──────────────────────────────────────────────────────────

@router.get("/test-case-types", response_model=list[TestCaseTypeRead])
async def list_test_case_types(db: DBSession, current_user: CurrentUser, active_only: bool = False):
    return await TestCaseTypeService(db).list(active_only=active_only)


@router.post("/test-case-types", response_model=TestCaseTypeRead, status_code=201)
async def create_test_case_type(data: TestCaseTypeCreate, db: DBSession, current_user: CurrentUser):
    obj = await TestCaseTypeService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/test-case-types/{entity_id}", response_model=TestCaseTypeRead)
async def update_test_case_type(entity_id: int, data: TestCaseTypeUpdate, db: DBSession, current_user: CurrentUser):
    obj = await TestCaseTypeService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/test-case-types/{entity_id}", response_model=MessageResponse)
async def deactivate_test_case_type(entity_id: int, db: DBSession, current_user: CurrentUser):
    await TestCaseTypeService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "Test Case Type deactivated"}


# ── Test Case Complexities ───────────────────────────────────────────────────

@router.get("/test-case-complexities", response_model=list[TestCaseComplexityRead])
async def list_test_case_complexities(db: DBSession, current_user: CurrentUser, active_only: bool = False):
    return await TestCaseComplexityService(db).list(active_only=active_only)


@router.post("/test-case-complexities", response_model=TestCaseComplexityRead, status_code=201)
async def create_test_case_complexity(data: TestCaseComplexityCreate, db: DBSession, current_user: CurrentUser):
    obj = await TestCaseComplexityService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/test-case-complexities/{entity_id}", response_model=TestCaseComplexityRead)
async def update_test_case_complexity(
    entity_id: int, data: TestCaseComplexityUpdate, db: DBSession, current_user: CurrentUser
):
    obj = await TestCaseComplexityService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/test-case-complexities/{entity_id}", response_model=MessageResponse)
async def deactivate_test_case_complexity(entity_id: int, db: DBSession, current_user: CurrentUser):
    await TestCaseComplexityService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "Test Case Complexity deactivated"}


# ── Environments ─────────────────────────────────────────────────────────────

@router.get("/environments", response_model=list[EnvironmentRead])
async def list_environments(db: DBSession, current_user: CurrentUser, active_only: bool = False):
    return await EnvironmentService(db).list(active_only=active_only)


@router.post("/environments", response_model=EnvironmentRead, status_code=201)
async def create_environment(data: EnvironmentCreate, db: DBSession, current_user: CurrentUser):
    obj = await EnvironmentService(db).create(data, current_user)
    await db.commit()
    return obj


@router.patch("/environments/{entity_id}", response_model=EnvironmentRead)
async def update_environment(entity_id: int, data: EnvironmentUpdate, db: DBSession, current_user: CurrentUser):
    obj = await EnvironmentService(db).update(entity_id, data, current_user)
    await db.commit()
    return obj


@router.delete("/environments/{entity_id}", response_model=MessageResponse)
async def deactivate_environment(entity_id: int, db: DBSession, current_user: CurrentUser):
    await EnvironmentService(db).deactivate(entity_id, current_user)
    await db.commit()
    return {"message": "Environment deactivated"}


# ── Relationships (M:N edges) ────────────────────────────────────────────────

@router.get("/relationships", response_model=list[TaxonomyRelationshipRead])
async def list_relationships(
    db: DBSession,
    current_user: CurrentUser,
    relation_type: str | None = None,
    from_id: int | None = None,
    to_id: int | None = None,
):
    return await TaxonomyRelationshipService(db).list(relation_type=relation_type, from_id=from_id, to_id=to_id)


@router.post("/relationships", response_model=TaxonomyRelationshipRead, status_code=201)
async def create_relationship(data: TaxonomyRelationshipCreate, db: DBSession, current_user: CurrentUser):
    obj = await TaxonomyRelationshipService(db).create(data, current_user)
    await db.commit()
    return obj


@router.delete("/relationships/{rel_id}", response_model=MessageResponse)
async def delete_relationship(rel_id: int, db: DBSession, current_user: CurrentUser):
    await TaxonomyRelationshipService(db).delete(rel_id, current_user)
    await db.commit()
    return {"message": "Relationship deleted"}
