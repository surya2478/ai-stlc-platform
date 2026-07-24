"""Shared free-text-to-taxonomy-ID resolution.

Used by both the test case CSV/XLSX importer (test_case_import_service.py)
and the AI generation pipeline's deterministic post-processing (agent_tasks.py
/ test_plans.py) — anywhere a free-text value (typed by a human, or inherited
from ProjectApplication) needs to be matched against a taxonomy master table
by exact name or code (case-insensitive), without asking an LLM to guess.
"""
from __future__ import annotations

from app.models.taxonomy import (
    Product,
    ProductGroup,
    QADomain,
    SubRequestType,
    System,
    TestCaseComplexity,
    TestCaseType,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Canonical field key -> taxonomy master table. Shared by the importer's
# column mapping and the agent pipeline's inherited-field mapping.
TAXONOMY_MODEL_BY_FIELD: dict[str, type] = {
    "domain": QADomain,
    "channel": System,
    "product": Product,
    "area_of_test": ProductGroup,
    "sub_request_type": SubRequestType,
    "test_case_type": TestCaseType,
    "test_case_complexity": TestCaseComplexity,
}


class TaxonomyResolver:
    """Resolves a taxonomy column's text value against its master table by
    exact name or code match (case-insensitive). Loads each table once per
    instance — construct one per request/run, not once at import time."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self._cache: dict[type, dict[str, int]] = {}

    async def _index(self, model: type) -> dict[str, int]:
        if model not in self._cache:
            rows = (await self.db.execute(select(model.id, model.name, model.code))).all()
            index: dict[str, int] = {}
            for row_id, name, code in rows:
                index[str(name).strip().lower()] = row_id
                index[str(code).strip().lower()] = row_id
            self._cache[model] = index
        return self._cache[model]

    async def resolve(self, model: type, value: str | None) -> int | None:
        if not value or not str(value).strip():
            return None
        index = await self._index(model)
        return index.get(str(value).strip().lower())

    async def resolve_field(self, field: str, value: str | None) -> int | None:
        """Resolve by canonical field key (see TAXONOMY_MODEL_BY_FIELD) rather
        than passing the model class directly."""
        model = TAXONOMY_MODEL_BY_FIELD.get(field)
        if model is None:
            return None
        return await self.resolve(model, value)


async def resolve_generated_test_case_taxonomy(resolver: TaxonomyResolver, tc_data: dict) -> dict:
    """Map a TestCaseDevelopmentAgent output dict to TestCase(...) kwargs for
    the taxonomy-linked fields.

    `test_case_type` / `test_case_complexity` come from the LLM (closed
    vocabulary, see TESTCASE_SYSTEM in test_case_agent.py) — resolved to their
    taxonomy IDs, with the legacy free-text column kept as a fallback only if
    the value somehow doesn't match (it should always match; the prompt
    constrains the vocabulary to exactly what's seeded).

    `domain` / `channel` / `product` / `area_of_test` are inherited
    deterministically from the project's application (see
    test_case_agent.py's `_inherited_*` stamping) — never LLM-generated.
    """
    test_type = tc_data.get("test_type")
    complexity = tc_data.get("complexity")
    domain = tc_data.get("_inherited_domain")
    channel = tc_data.get("_inherited_channel")
    product = tc_data.get("_inherited_product")
    area_of_test = tc_data.get("_inherited_area_of_test")

    test_case_type_id = await resolver.resolve_field("test_case_type", test_type)
    test_case_complexity_id = await resolver.resolve_field("test_case_complexity", complexity)
    domain_id = await resolver.resolve_field("domain", domain)
    channel_id = await resolver.resolve_field("channel", channel)
    product_id = await resolver.resolve_field("product", product)
    area_of_test_id = await resolver.resolve_field("area_of_test", area_of_test)

    return {
        "application_id": tc_data.get("_inherited_application_id"),
        "test_case_type_id": test_case_type_id,
        "test_case_complexity_id": test_case_complexity_id,
        "domain_id": domain_id,
        "channel_id": channel_id,
        "product_id": product_id,
        "area_of_test_id": area_of_test_id,
        # Legacy free-text fallbacks — kept for backward-compatible display
        # wherever the *_id FK isn't resolved yet (e.g. taxonomy not seeded).
        "telecom_domain": None if domain_id else domain,
        "product": None if product_id else product,
        "product_group": None if area_of_test_id else area_of_test,
        "is_critical": bool(tc_data.get("is_critical", False)),
        "test_case_objective": tc_data.get("objective") or None,
    }
