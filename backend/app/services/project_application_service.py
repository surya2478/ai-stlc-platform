from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import Project
from app.models.project_application import ProjectApplication, ProjectExternalDependency
from app.models.project_membership import ProjectMembership
from app.models.llm_settings import ProjectSettingAuditLog
from app.models.requirement import Requirement
from app.models.test_case import TestCase
from app.schemas.applications import (
    ApplicationMappingConflict,
    ProjectApplicationUpdate,
    ProjectApplicationsSummary,
    ProjectApplicationsUpdateRequest,
    ProjectExternalDependencyUpdate,
    ProjectExternalDependenciesUpdateRequest,
)

_FALLBACK_ENVIRONMENTS = ["development", "staging", "production", "ci"]

# The 8 canonical applications every project must be able to seed
# idempotently (contract §11). Keys are given in the lowercase-slug form
# ProjectApplicationUpdate.validate_key already normalizes every key to
# (matching every other application in this system, e.g. "cust-portal") —
# the contract's "APP-CUSTOMER-PORTAL" wording describes a display
# convention, not the enforced storage format. Seeding never overwrites an
# existing row for a key already present — see seed_canonical_applications().
CANONICAL_APPLICATIONS = (
    ("app-usp-direct", "USP Direct"),
    ("app-b2b", "B2B"),
    ("app-cim", "CIM"),
    ("app-code", "CoDE"),
    ("app-b2c", "B2C"),
    ("app-sales-portal", "Sales Portal"),
    ("app-smiles", "Smiles"),
    ("app-mobile-app", "Mobile App"),
)


def _application_snapshot(app: ProjectApplication) -> dict[str, Any]:
    return {
        "id": app.id,
        "project_id": app.project_id,
        "key": app.key,
        "name": app.name,
        "description": app.description,
        "is_default": app.is_default,
        "environment_urls": app.environment_urls or {},
        "is_active": app.is_active,
        "application_type": app.application_type,
        "aliases": app.aliases or [],
        "lifecycle_status": app.lifecycle_status,
        "business_owner_id": app.business_owner_id,
        "technical_owner_id": app.technical_owner_id,
        "domain": app.domain,
        "product_group": app.product_group,
        "product": app.product,
        "channel": app.channel,
        "updated_by": app.updated_by,
        "updated_at": app.updated_at.isoformat() if app.updated_at else None,
    }


async def _validate_owner_references(
    db: AsyncSession, project_id: int, updates: list[ProjectApplicationUpdate]
) -> None:
    """Owner references must be real, authorized project members — not
    free-text names. `Project.owner_id` is always authorized even without an
    explicit membership row (mirrors the RBAC check in api/deps.py)."""
    owner_ids = {
        owner_id
        for item in updates
        for owner_id in (item.business_owner_id, item.technical_owner_id)
        if owner_id is not None
    }
    if not owner_ids:
        return

    result = await db.execute(
        select(ProjectMembership.user_id).where(
            ProjectMembership.project_id == project_id,
            ProjectMembership.user_id.in_(owner_ids),
            ProjectMembership.is_active.is_(True),
        )
    )
    authorized_ids = set(result.scalars().all())

    project = await db.get(Project, project_id)
    if project and project.owner_id in owner_ids:
        authorized_ids.add(project.owner_id)

    unauthorized = owner_ids - authorized_ids
    if unauthorized:
        raise HTTPException(
            status_code=422,
            detail=f"Owner reference(s) are not authorized members of this project: {sorted(unauthorized)}",
        )


def _dependency_snapshot(dep: ProjectExternalDependency) -> dict[str, Any]:
    return {
        "id": dep.id,
        "project_id": dep.project_id,
        "application_id": dep.application_id,
        "service_name": dep.service_name,
        "note": dep.note,
        "sandbox_url": dep.sandbox_url,
        "mock_strategy": dep.mock_strategy,
        "is_active": dep.is_active,
        "updated_by": dep.updated_by,
        "updated_at": dep.updated_at.isoformat() if dep.updated_at else None,
    }


def _validate_application_updates(updates: list[ProjectApplicationUpdate]) -> None:
    keys = [item.key for item in updates]
    dupes = {k for k in keys if keys.count(k) > 1}
    if dupes:
        raise HTTPException(status_code=422, detail=f"Duplicate application key(s): {', '.join(sorted(dupes))}")

    defaults = [item for item in updates if item.is_default and item.is_active]
    if len(defaults) > 1:
        raise HTTPException(status_code=400, detail="Only one application can be the default per project.")


def _synced_lifecycle_status(lifecycle_status: str, is_active: bool) -> tuple[str, bool]:
    """Keep lifecycle_status and is_active mutually consistent: a deprecated
    or retired application cannot be active, and an inactive application
    cannot claim the "active" lifecycle state."""
    if lifecycle_status in ("deprecated", "retired"):
        return lifecycle_status, False
    if lifecycle_status == "active" and not is_active:
        return "draft", is_active
    return lifecycle_status, is_active


async def list_applications(db: AsyncSession, project_id: int) -> list[ProjectApplication]:
    result = await db.execute(
        select(ProjectApplication)
        .where(ProjectApplication.project_id == project_id)
        .order_by(ProjectApplication.name.asc())
    )
    return list(result.scalars().all())


async def list_external_dependencies(db: AsyncSession, project_id: int) -> list[ProjectExternalDependency]:
    result = await db.execute(
        select(ProjectExternalDependency)
        .where(ProjectExternalDependency.project_id == project_id)
        .order_by(ProjectExternalDependency.service_name.asc())
    )
    return list(result.scalars().all())


async def resolve_default_application(db: AsyncSession, project_id: int) -> ProjectApplication | None:
    result = await db.execute(
        select(ProjectApplication).where(
            ProjectApplication.project_id == project_id,
            ProjectApplication.is_default.is_(True),
            ProjectApplication.is_active.is_(True),
        )
    )
    return result.scalar_one_or_none()


def configured_environments(application: ProjectApplication | None) -> list[str]:
    """Environment names this application actually has a URL for.

    Callers report this when the environment asked for has none: "no URL is
    configured" leaves a user hunting through project settings, while "no URL
    for 'qa'; this application has one for 'SIT'" names the fix.
    """
    if not application or not application.environment_urls:
        return []
    return sorted(
        str(name)
        for name, url in application.environment_urls.items()
        if isinstance(url, str) and url.strip()
    )


def resolve_environment_url(application: ProjectApplication | None, environment: str | None) -> str | None:
    """The application's URL for one environment, matched without regard to case.

    An exact-key lookup meant "sit" found nothing while "SIT" resolved, which
    is not a distinction anyone types deliberately. Environment names are
    entered free-form in several places in the platform and stored as the user
    wrote them, so the same environment reaches this function capitalised
    differently depending on which screen set it.

    Deliberately still fails when the environment is genuinely absent: falling
    back to some other environment's URL would run a QA suite against whatever
    happened to be configured, which is worse than reporting that nothing is.
    """
    if not application or not application.environment_urls or not environment:
        return None
    urls = application.environment_urls
    url = urls.get(environment)
    if not (isinstance(url, str) and url.strip()):
        wanted = environment.strip().casefold()
        url = next(
            (
                value
                for name, value in urls.items()
                if str(name).strip().casefold() == wanted
                and isinstance(value, str)
                and value.strip()
            ),
            None,
        )
    return url.strip() if isinstance(url, str) and url.strip() else None


async def resolve_application_context(
    db: AsyncSession, *, project_id: int, requirement: Requirement | None
) -> dict:
    """Resolve a real application URL (+ any scraped page analysis) to ground
    AI-generated scenario/test-case text, instead of letting the LLM invent a
    placeholder domain like example.com.

    Precedence: the requirement's own scraped source_url (most specific — the
    actual page the requirement came from) and its ui_analysis, then the
    project's default ProjectApplication URL, else nothing (callers must
    instruct the user to configure one).

    Also resolves the project's default application's classification fields
    (application_id, domain, channel, product, product_group) regardless of
    which URL source was used — these are project/application-level facts,
    not tied to a specific scraped page, and let callers deterministically
    inherit Domain/Channel/Product/Area of Test onto generated test cases
    instead of asking the LLM to guess them (there's no per-requirement
    application link today, only a project default).
    """
    application = await resolve_default_application(db, project_id)
    app_fields = {
        "application_id": application.id if application else None,
        "domain": application.domain if application else None,
        "channel": application.channel if application else None,
        "product": application.product if application else None,
        "product_group": application.product_group if application else None,
    }

    metadata = (requirement.metadata_ or {}) if requirement else {}
    source_url = metadata.get("source_url")
    if isinstance(source_url, str) and source_url.strip():
        return {
            "url": source_url.strip(),
            "source": "requirement",
            "ui_analysis": metadata.get("ui_analysis"),
            **app_fields,
        }

    if application and application.environment_urls:
        # Text grounding doesn't need per-environment precision — pick any
        # configured URL; the execution-time chain (automation_tasks.py)
        # already re-resolves the correct one per run.environment for actual
        # script runs.
        url = next(
            (v.strip() for v in application.environment_urls.values() if isinstance(v, str) and v.strip()),
            None,
        )
        if url:
            return {"url": url, "source": "project_default", "ui_analysis": None, **app_fields}

    return {"url": None, "source": None, "ui_analysis": None, **app_fields}


async def build_test_case_application_context(db: AsyncSession, tc: TestCase) -> dict:
    """Resolve the application a test case targets (falling back to the
    project's default application when untagged) so script generation can be
    told a real application exists instead of inventing a placeholder domain.

    Deliberately does NOT resolve an environment-specific URL here — that
    stays exclusively at execution time (automation_tasks.py), which already
    re-resolves per run.environment. Generation only needs to know whether a
    real base URL will be available and what to mock.
    """
    application: ProjectApplication | None = None
    if tc.application_id:
        application = await db.get(ProjectApplication, tc.application_id)
    if application is None:
        application = await resolve_default_application(db, tc.project_id)

    external_dependencies: list[dict] = []
    if application is not None:
        result = await db.execute(
            select(ProjectExternalDependency).where(
                ProjectExternalDependency.project_id == tc.project_id,
                ProjectExternalDependency.is_active.is_(True),
                (ProjectExternalDependency.application_id == application.id)
                | (ProjectExternalDependency.application_id.is_(None)),
            )
        )
        external_dependencies = [
            {
                "service_name": dep.service_name,
                "mock_strategy": dep.mock_strategy,
                "sandbox_url": dep.sandbox_url,
            }
            for dep in result.scalars().all()
        ]

    return {
        "application_name": application.name if application else None,
        "has_configured_base_url": bool(application and application.environment_urls),
        "external_dependencies": external_dependencies,
    }


async def build_project_applications_response(db: AsyncSession, project_id: int) -> dict:
    applications = await list_applications(db, project_id)
    dependencies = await list_external_dependencies(db, project_id)

    available_environments = sorted({env for app in applications for env in (app.environment_urls or {})})
    if not available_environments:
        available_environments = list(_FALLBACK_ENVIRONMENTS)

    all_rows = [*applications, *dependencies]
    last_updated_row = max(all_rows, key=lambda r: r.updated_at or r.created_at, default=None)

    return {
        "project_id": project_id,
        "applications": applications,
        "external_dependencies": dependencies,
        "available_environments": available_environments,
        "last_updated": last_updated_row.updated_at if last_updated_row else None,
        "updated_by": last_updated_row.updated_by if last_updated_row else None,
    }


async def update_project_applications(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectApplicationsUpdateRequest,
    user_id: int,
    source: str = "ui",
) -> dict:
    _validate_application_updates(payload.applications)
    await _validate_owner_references(db, project_id, payload.applications)

    existing = {item.key: item for item in await list_applications(db, project_id)}
    old_snapshot = [_application_snapshot(item) for item in existing.values()]

    payload_keys = {item.key for item in payload.applications}
    new_default_keys = {item.key for item in payload.applications if item.is_default and item.is_active}

    for item in payload.applications:
        row = existing.get(item.key)
        if row is None:
            row = ProjectApplication(project_id=project_id, key=item.key, created_by=user_id)
            db.add(row)
        lifecycle_status, is_active = _synced_lifecycle_status(item.lifecycle_status, item.is_active)
        row.name = item.name
        row.description = item.description
        row.environment_urls = item.environment_urls
        row.is_active = is_active
        row.is_default = item.is_default and is_active
        row.application_type = item.application_type
        row.aliases = item.aliases
        row.lifecycle_status = lifecycle_status
        row.business_owner_id = item.business_owner_id
        row.technical_owner_id = item.technical_owner_id
        row.domain = item.domain
        row.product_group = item.product_group
        row.product = item.product
        row.channel = item.channel
        row.updated_by = user_id

    # Clear default on any untouched row when a new default was set in this payload.
    if new_default_keys:
        for key, row in existing.items():
            if key not in payload_keys:
                row.is_default = False

    await db.flush()
    new_rows = await list_applications(db, project_id)
    audit = ProjectSettingAuditLog(
        project_id=project_id,
        setting_type="applications",
        old_value={"applications": old_snapshot},
        new_value={"applications": [_application_snapshot(item) for item in new_rows]},
        changed_by=user_id,
        source=source,
        change_reason=payload.change_reason,
    )
    db.add(audit)
    await db.flush()
    return await build_project_applications_response(db, project_id)


async def list_application_audit_log(db: AsyncSession, project_id: int, limit: int = 100) -> list[ProjectSettingAuditLog]:
    """Real change history for the Application Registry (UI-014 History and
    Activity inspector tabs) — the existing whole-payload before/after
    snapshots written by update_project_applications /
    update_project_external_dependencies / seed_canonical_applications.
    Diffing down to a per-field view happens client-side."""
    result = await db.execute(
        select(ProjectSettingAuditLog)
        .where(
            ProjectSettingAuditLog.project_id == project_id,
            ProjectSettingAuditLog.setting_type.in_(("applications", "external_dependencies")),
        )
        .order_by(ProjectSettingAuditLog.changed_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())


async def build_registry_summary(db: AsyncSession, project_id: int) -> ProjectApplicationsSummary:
    """Application Registry (UI-014) KPI aggregates. `discovery_ready` is a
    disclosed proxy — the contract's own gate (>=1 active environment with a
    valid URL) — not real discovery-session telemetry, since no discovery
    subsystem exists yet. `mapping_conflicts` only considers applications
    that actually have a product_group/product/channel mapped."""
    applications = await list_applications(db, project_id)

    active = [app for app in applications if app.is_active]
    discovery_ready = [app for app in active if app.environment_urls]
    environment_gaps = [app for app in active if not app.environment_urls]

    conflict_groups: dict[tuple[str | None, str | None, str | None], list[int]] = {}
    for app in active:
        if not (app.product_group or app.product or app.channel):
            continue
        key = (app.product_group, app.product, app.channel)
        conflict_groups.setdefault(key, []).append(app.id)
    mapping_conflicts = [
        ApplicationMappingConflict(
            product_group=key[0], product=key[1], channel=key[2], application_ids=sorted(ids)
        )
        for key, ids in conflict_groups.items()
        if len(ids) > 1
    ]

    usage_result = await db.execute(
        select(TestCase.application_id, func.count(TestCase.id))
        .where(TestCase.project_id == project_id, TestCase.application_id.isnot(None))
        .group_by(TestCase.application_id)
    )
    mapping_usage = {app_id: count for app_id, count in usage_result.all()}

    return ProjectApplicationsSummary(
        project_id=project_id,
        total_applications=len(applications),
        active_applications=len(active),
        discovery_ready=len(discovery_ready),
        environment_gaps=len(environment_gaps),
        mapping_conflicts=mapping_conflicts,
        mapping_usage=mapping_usage,
    )


async def seed_canonical_applications(db: AsyncSession, project_id: int, user_id: int) -> dict:
    """Idempotently seed the 8 canonical applications (contract §11) for a
    project. Only keys not already present are inserted — an authorized
    user's prior edits to an already-seeded row (or a row they created with
    the same key) are never overwritten, since we simply omit that key from
    the payload passed to update_project_applications."""
    existing_keys = {item.key for item in await list_applications(db, project_id)}
    missing = [
        ProjectApplicationUpdate(key=key, name=name)
        for key, name in CANONICAL_APPLICATIONS
        if key not in existing_keys
    ]
    if not missing:
        return await build_project_applications_response(db, project_id)

    # Only the missing keys are submitted — update_project_applications
    # leaves every row absent from the payload untouched, EXCEPT it clears
    # is_default on untouched rows if the payload sets a new default. Since
    # seeded rows never set is_default=True, that side effect never fires,
    # so existing applications (including ones a user has since edited) are
    # never read from the DB and never rewritten by this call.
    payload = ProjectApplicationsUpdateRequest(
        applications=[
            ProjectApplicationUpdate(
                key=item.key,
                name=item.name,
                description=None,
                is_default=False,
                environment_urls={},
                is_active=True,
            )
            for item in missing
        ],
        change_reason="Seeded canonical applications",
    )
    return await update_project_applications(db, project_id=project_id, payload=payload, user_id=user_id, source="seed")


async def update_project_external_dependencies(
    db: AsyncSession,
    *,
    project_id: int,
    payload: ProjectExternalDependenciesUpdateRequest,
    user_id: int,
    source: str = "ui",
) -> dict:
    existing = {item.id: item for item in await list_external_dependencies(db, project_id)}
    old_snapshot = [_dependency_snapshot(item) for item in existing.values()]

    kept_ids: set[int] = set()
    for item in payload.dependencies:
        row = None
        item_id = getattr(item, "id", None)
        if item_id is not None:
            row = existing.get(item_id)
        if row is None:
            row = ProjectExternalDependency(project_id=project_id, created_by=user_id)
            db.add(row)
        else:
            kept_ids.add(row.id)
        row.application_id = item.application_id
        row.service_name = item.service_name
        row.note = item.note
        row.sandbox_url = item.sandbox_url
        row.mock_strategy = item.mock_strategy
        row.is_active = item.is_active
        row.updated_by = user_id

    # Rows present before this update but omitted from the payload are treated
    # as removed — soft-delete via is_active rather than a hard DELETE so any
    # historical audit snapshot referencing them stays meaningful.
    for dep_id, row in existing.items():
        if dep_id not in kept_ids:
            row.is_active = False
            row.updated_by = user_id

    await db.flush()
    new_rows = await list_external_dependencies(db, project_id)
    audit = ProjectSettingAuditLog(
        project_id=project_id,
        setting_type="external_dependencies",
        old_value={"dependencies": old_snapshot},
        new_value={"dependencies": [_dependency_snapshot(item) for item in new_rows]},
        changed_by=user_id,
        source=source,
        change_reason=payload.change_reason,
    )
    db.add(audit)
    await db.flush()
    return await build_project_applications_response(db, project_id)
