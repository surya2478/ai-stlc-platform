"""Execution groups — suite-owned grouping of members (Phase B).

Grouping is how a cross-member conflict gets resolved without touching
anything at source: two frameworks in one suite stop being a contradiction once
each is its own group. Nothing here writes to a test case, script, Application
Model or environment.

`plan_auto_split` is pure so the split can be previewed and tested without a
database.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_suite import (
    AutomationSuite,
    AutomationSuiteExecutionGroup,
    AutomationSuiteTestCase,
)
from app.services.automation_suite.errors import AutomationSuiteError
from app.services.automation_suite.inheritance import MemberInheritance

# What a suite may be split by. Each is an inherited discriminator already
# resolved onto the member row, so a split never needs new user input.
SPLIT_DIMENSIONS = ("framework", "environment", "application")


@dataclass(frozen=True)
class PlannedGroup:
    name: str
    framework: str | None
    environment: str | None
    application_id: int | None
    member_ids: tuple[int, ...]
    sequence: int


def _discriminator(member: MemberInheritance, dimension: str) -> tuple[str, Any]:
    if dimension == "framework":
        framework = member.primary_script.framework if member.primary_script else None
        return (framework or "unmapped", framework)
    if dimension == "environment":
        return (member.resolved_environment or "unresolved", member.resolved_environment)
    if dimension == "application":
        app = member.application
        return (app.key if app else "unmapped", app.id if app else None)
    raise AutomationSuiteError(
        422, "UNKNOWN_SPLIT_DIMENSION", f"Cannot split by '{dimension}'."
    )


def plan_auto_split(members: list[MemberInheritance], *, dimension: str) -> list[PlannedGroup]:
    """One group per distinct value of the chosen dimension.

    Excluded members are left out entirely; manual-only members are grouped
    too, because a manual group is still a real execution grouping decision.
    """
    if dimension not in SPLIT_DIMENSIONS:
        raise AutomationSuiteError(
            422,
            "UNKNOWN_SPLIT_DIMENSION",
            f"Split dimension must be one of {', '.join(SPLIT_DIMENSIONS)}.",
        )

    eligible = [m for m in members if m.member.inclusion_status != "excluded"]
    buckets: dict[str, list[MemberInheritance]] = {}
    values: dict[str, Any] = {}
    for member in eligible:
        label, value = _discriminator(member, dimension)
        buckets.setdefault(label, []).append(member)
        values[label] = value

    planned: list[PlannedGroup] = []
    for sequence, label in enumerate(sorted(buckets), start=1):
        bucket = buckets[label]
        value = values[label]
        planned.append(
            PlannedGroup(
                name=f"{dimension.capitalize()}: {label}",
                framework=value if dimension == "framework" else None,
                environment=value if dimension == "environment" else None,
                application_id=value if dimension == "application" else None,
                member_ids=tuple(m.member_id for m in bucket),
                sequence=sequence,
            )
        )
    return planned


async def list_groups(db: AsyncSession, suite: AutomationSuite) -> list[dict[str, Any]]:
    result = await db.execute(
        select(AutomationSuiteExecutionGroup)
        .where(AutomationSuiteExecutionGroup.suite_id == suite.id)
        .order_by(AutomationSuiteExecutionGroup.sequence, AutomationSuiteExecutionGroup.id)
    )
    groups = list(result.scalars().all())

    counts: dict[int, int] = {}
    if groups:
        rows = await db.execute(
            select(AutomationSuiteTestCase.execution_group_id, func.count())
            .where(AutomationSuiteTestCase.suite_id == suite.id)
            .group_by(AutomationSuiteTestCase.execution_group_id)
        )
        counts = {gid: n for gid, n in rows.all() if gid is not None}

    ungrouped = (
        await db.execute(
            select(func.count())
            .select_from(AutomationSuiteTestCase)
            .where(
                AutomationSuiteTestCase.suite_id == suite.id,
                AutomationSuiteTestCase.execution_group_id.is_(None),
                AutomationSuiteTestCase.inclusion_status != "excluded",
            )
        )
    ).scalar() or 0

    return [
        {
            "id": g.id,
            "name": g.name,
            "sequence": g.sequence,
            "status": g.status,
            "framework": g.framework,
            "environment": g.environment,
            "application_id": g.application_id,
            "notes": g.notes,
            "member_count": counts.get(g.id, 0),
            "created_at": g.created_at,
        }
        for g in groups
    ] + (
        [
            {
                "id": None,
                "name": "Ungrouped",
                "sequence": 999,
                "status": "draft",
                "framework": None,
                "environment": None,
                "application_id": None,
                "notes": "Members not yet assigned to an execution group.",
                "member_count": ungrouped,
                "created_at": None,
            }
        ]
        if ungrouped
        else []
    )


async def get_group_or_404(
    db: AsyncSession, suite: AutomationSuite, group_id: int
) -> AutomationSuiteExecutionGroup:
    row = await db.get(AutomationSuiteExecutionGroup, group_id)
    if row is None or row.suite_id != suite.id:
        raise AutomationSuiteError(404, "GROUP_NOT_FOUND", "Execution group not found on this suite.")
    return row


async def create_group(
    db: AsyncSession,
    suite: AutomationSuite,
    *,
    name: str,
    framework: str | None = None,
    environment: str | None = None,
    application_id: int | None = None,
    notes: str | None = None,
    sequence: int | None = None,
    actor_id: int,
) -> AutomationSuiteExecutionGroup:
    clean_name = (name or "").strip()
    if not clean_name:
        raise AutomationSuiteError(422, "GROUP_NAME_REQUIRED", "An execution group needs a name.")

    if sequence is None:
        highest = (
            await db.execute(
                select(func.coalesce(func.max(AutomationSuiteExecutionGroup.sequence), 0)).where(
                    AutomationSuiteExecutionGroup.suite_id == suite.id
                )
            )
        ).scalar() or 0
        sequence = int(highest) + 1

    group = AutomationSuiteExecutionGroup(
        suite_id=suite.id,
        name=clean_name,
        sequence=sequence,
        status="draft",
        framework=framework,
        environment=environment,
        application_id=application_id,
        notes=notes,
        created_by=actor_id,
    )
    db.add(group)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        raise AutomationSuiteError(
            409, "GROUP_NAME_EXISTS", f"This suite already has an execution group named '{clean_name}'."
        )
    return group


async def assign_members(
    db: AsyncSession, suite: AutomationSuite, *, group_id: int | None, member_ids: list[int]
) -> int:
    """Point members at a group, or at None to ungroup them."""
    if not member_ids:
        return 0
    result = await db.execute(
        select(AutomationSuiteTestCase).where(
            AutomationSuiteTestCase.suite_id == suite.id,
            AutomationSuiteTestCase.id.in_(member_ids),
        )
    )
    members = list(result.scalars().all())
    for member in members:
        member.execution_group_id = group_id
    await db.flush()
    return len(members)


async def clear_groups(db: AsyncSession, suite: AutomationSuite) -> None:
    """Detach every member then delete the suite's groups."""
    result = await db.execute(
        select(AutomationSuiteTestCase).where(AutomationSuiteTestCase.suite_id == suite.id)
    )
    for member in result.scalars().all():
        member.execution_group_id = None
    await db.flush()

    groups = await db.execute(
        select(AutomationSuiteExecutionGroup).where(AutomationSuiteExecutionGroup.suite_id == suite.id)
    )
    for group in groups.scalars().all():
        await db.delete(group)
    await db.flush()
