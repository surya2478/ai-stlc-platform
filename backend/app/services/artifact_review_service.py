"""Persistence and lookup helpers for generic reviewer-agent output (Phase 1)."""
from __future__ import annotations

from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.artifact_review import ArtifactReview
from app.models.project import Project

VALID_VERDICTS = ("pass", "needs_revision", "fail")


async def get_review_mode(db: AsyncSession, project_id: int) -> str:
    project = await db.get(Project, project_id)
    return project.review_mode if project else "advisory"


async def create_review(
    db: AsyncSession,
    *,
    project_id: int,
    agent_run_id: int | None,
    artifact_type: str,
    artifact_id: int,
    reviewer_agent: str,
    scores: dict[str, float] | None,
    overall_score: float | None,
    verdict: str,
    findings: list[dict[str, Any]] | None,
    coverage_gaps: list[dict[str, Any]] | None,
    review_mode: str,
) -> ArtifactReview:
    review = ArtifactReview(
        project_id=project_id,
        agent_run_id=agent_run_id,
        artifact_type=artifact_type,
        artifact_id=artifact_id,
        reviewer_agent=reviewer_agent,
        scores=scores,
        overall_score=overall_score,
        verdict=verdict if verdict in VALID_VERDICTS else "needs_revision",
        findings=findings,
        coverage_gaps=coverage_gaps,
        review_mode=review_mode,
    )
    db.add(review)
    await db.flush()
    return review


async def latest_reviews(
    db: AsyncSession, *, artifact_type: str, artifact_ids: list[int]
) -> dict[int, ArtifactReview]:
    """Most recent review per artifact_id — used by both gating checks and UI badges."""
    if not artifact_ids:
        return {}
    result = await db.execute(
        select(ArtifactReview)
        .where(ArtifactReview.artifact_type == artifact_type, ArtifactReview.artifact_id.in_(artifact_ids))
        .order_by(ArtifactReview.artifact_id, desc(ArtifactReview.created_at))
    )
    latest: dict[int, ArtifactReview] = {}
    for row in result.scalars().all():
        if row.artifact_id not in latest:
            latest[row.artifact_id] = row
    return latest


async def latest_review_for(db: AsyncSession, *, artifact_type: str, artifact_id: int) -> ArtifactReview | None:
    reviews = await latest_reviews(db, artifact_type=artifact_type, artifact_ids=[artifact_id])
    return reviews.get(artifact_id)


async def latest_reviews_for_project(
    db: AsyncSession, *, project_id: int, artifact_type: str | None = None
) -> list[ArtifactReview]:
    """Most recent review per (artifact_type, artifact_id) across a whole
    project — feeds the review badge overlay on Scenario/Test Case tables."""
    stmt = (
        select(ArtifactReview)
        .where(ArtifactReview.project_id == project_id)
        .order_by(ArtifactReview.artifact_type, ArtifactReview.artifact_id, desc(ArtifactReview.created_at))
    )
    if artifact_type:
        stmt = stmt.where(ArtifactReview.artifact_type == artifact_type)
    result = await db.execute(stmt)
    seen: set[tuple[str, int]] = set()
    latest: list[ArtifactReview] = []
    for row in result.scalars().all():
        key = (row.artifact_type, row.artifact_id)
        if key in seen:
            continue
        seen.add(key)
        latest.append(row)
    return latest


async def review_history(db: AsyncSession, *, artifact_type: str, artifact_id: int) -> list[ArtifactReview]:
    """Full review history for one artifact, newest first — feeds the findings drawer."""
    result = await db.execute(
        select(ArtifactReview)
        .where(ArtifactReview.artifact_type == artifact_type, ArtifactReview.artifact_id == artifact_id)
        .order_by(desc(ArtifactReview.created_at))
    )
    return list(result.scalars().all())
