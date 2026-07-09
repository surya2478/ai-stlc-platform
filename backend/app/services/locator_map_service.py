"""Persistence helpers for the locator_map knowledge base (Phase 3).

Upserted by (application_id, page, element_name) — re-discovery refreshes an
existing row's confidence/last_validated_at rather than accumulating
duplicates, matching the unique constraint in migration 033.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.locator_map import LocatorMapEntry


async def upsert_locator(
    db: AsyncSession,
    *,
    project_id: int,
    application_id: int | None,
    page: str,
    element_name: str,
    recommended_locator: str,
    recommended_strategy: str,
    business_meaning: str | None = None,
    fallback_locator: str | None = None,
    confidence_score: int = 0,
) -> LocatorMapEntry:
    result = await db.execute(
        select(LocatorMapEntry).where(
            LocatorMapEntry.application_id == application_id,
            LocatorMapEntry.page == page,
            LocatorMapEntry.element_name == element_name,
        )
    )
    entry = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if entry is None:
        entry = LocatorMapEntry(
            project_id=project_id,
            application_id=application_id,
            page=page,
            element_name=element_name,
            recommended_locator=recommended_locator,
            recommended_strategy=recommended_strategy,
            business_meaning=business_meaning,
            fallback_locator=fallback_locator,
            confidence_score=confidence_score,
            last_validated_at=now,
        )
        db.add(entry)
    else:
        entry.recommended_locator = recommended_locator
        entry.recommended_strategy = recommended_strategy
        if business_meaning:
            entry.business_meaning = business_meaning
        if fallback_locator:
            entry.fallback_locator = fallback_locator
        entry.confidence_score = confidence_score
        entry.last_validated_at = now
    await db.flush()
    return entry


async def record_script_usage(db: AsyncSession, entry: LocatorMapEntry, script_id: int) -> None:
    used = list(entry.used_by_scripts or [])
    if script_id not in used:
        used.append(script_id)
        entry.used_by_scripts = used
        await db.flush()


async def record_failure(db: AsyncSession, entry: LocatorMapEntry) -> None:
    entry.failure_count = (entry.failure_count or 0) + 1
    await db.flush()


async def list_for_application(
    db: AsyncSession, *, project_id: int, application_id: int | None = None
) -> list[LocatorMapEntry]:
    stmt = select(LocatorMapEntry).where(LocatorMapEntry.project_id == project_id)
    if application_id is not None:
        stmt = stmt.where(LocatorMapEntry.application_id == application_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())
