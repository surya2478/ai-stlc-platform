"""Business Process master table — wiring and the migration's code derivation.

The repo has no DB-backed test fixture, so this covers what can go wrong
without one: a slug rule that produces codes the schema would then reject, and
a new entity that is registered in one place but not the others.
"""
import importlib.util
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.models.taxonomy import BusinessProcess
from app.schemas.taxonomy import (
    RELATION_ENDPOINTS,
    BusinessProcessCreate,
    BusinessProcessRead,
    TaxonomyTree,
)
from app.services.taxonomy_service import (
    _MODEL_BY_ENTITY,
    BusinessProcessService,
)


def _load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "060_business_process_taxonomy.py"
    spec = importlib.util.spec_from_file_location("migration_060", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


migration = _load_migration()


# ── Seed code derivation ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "name,expected",
    [
        ("Sales", "SALES"),
        ("User registration", "USER_REGISTRATION"),
        ("Order to Cash", "ORDER_TO_CASH"),
        ("Order-to-Cash", "ORDER_TO_CASH"),
        ("  Billing   Dispute  ", "BILLING_DISPUTE"),
        ("Fibre / Broadband", "FIBRE_BROADBAND"),
        ("B2B (Enterprise)", "B2B_ENTERPRISE"),
    ],
)
def test_seed_code_is_derived_from_the_name(name, expected):
    assert migration._code_for(name) == expected


def test_derived_code_always_survives_the_schema_validator():
    """The seeder writes codes straight to SQL; the API validates them later.

    A name that slugged to something the validator rejects would create a row
    nobody could subsequently edit through the API.
    """
    for name in ("Order to Cash", "Fibre / Broadband", "B2B (Enterprise)", "Prépaid & Postpaid"):
        code = migration._code_for(name)
        entry = BusinessProcessCreate(name=name, code=code)
        assert entry.code == code


def test_a_name_with_no_usable_characters_still_yields_a_code():
    assert migration._code_for("!!!") == "BUSINESS_PROCESS"
    assert migration._code_for("") == "BUSINESS_PROCESS"


def test_derived_code_fits_the_column():
    long_name = "Enterprise " * 20
    assert len(migration._code_for(long_name)) <= 60


# ── Wiring ───────────────────────────────────────────────────────────────────

def test_service_is_bound_to_the_business_process_model():
    assert BusinessProcessService.model is BusinessProcess
    assert BusinessProcessService.label == "Business Process"
    assert BusinessProcess.__tablename__ == "business_processes"


def test_entity_is_registered_for_polymorphic_relationship_endpoints():
    assert _MODEL_BY_ENTITY["business_process"] is BusinessProcess
    # Registering the entity must not invent edges nothing asked for.
    assert "business_process" not in {e for pair in RELATION_ENDPOINTS.values() for e in pair}


def test_tree_carries_business_processes_and_defaults_to_empty():
    assert TaxonomyTree().business_processes == []
    tree = TaxonomyTree(
        business_processes=[
            BusinessProcessRead(
                id=1,
                name="Sales",
                code="SALES",
                created_at="2026-08-05T00:00:00Z",
                updated_at="2026-08-05T00:00:00Z",
            )
        ]
    )
    assert [b.name for b in tree.business_processes] == ["Sales"]


def test_blank_name_is_rejected():
    with pytest.raises(ValidationError):
        BusinessProcessCreate(name="   ", code="SALES")


# ── Edit serialisation ───────────────────────────────────────────────────────

def test_every_taxonomy_edit_reloads_before_serialising():
    """`updated_at` has onupdate=func.now(), so an edited row comes back with
    that attribute expired. Serialising it without a refresh triggers a lazy
    load on the async engine and 500s (MissingGreenlet) — which is what every
    taxonomy PATCH did before `_commit_updated`.
    """
    import inspect

    from app.api.v1.endpoints import taxonomy as endpoints

    patch_handlers = [
        obj
        for name, obj in vars(endpoints).items()
        if name.startswith("update_") and inspect.iscoroutinefunction(obj)
    ]
    assert patch_handlers, "no PATCH handlers found — did the module move?"
    for handler in patch_handlers:
        source = inspect.getsource(handler)
        assert "_commit_updated" in source, f"{handler.__name__} serialises an edited row without refreshing"
