"""
Artifact review + coverage matrix endpoints (Phase 1).

Read-only surface for the stage reviewer agents' output — review badges and
findings drawers on the Scenario/Test Case tables, and the Coverage Matrix
view read from here.
"""
from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DBSession, require_project_access
from app.schemas.artifact_review import ArtifactReviewOut, CoverageMatrixEntryOut
from app.services import artifact_review_service, coverage_matrix_service

router = APIRouter()


@router.get("/project/{project_id}", response_model=list[ArtifactReviewOut])
async def list_latest_reviews(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    artifact_type: str | None = Query(None),
):
    """Most recent review per reviewed artifact — feeds table badges."""
    await require_project_access(project_id, current_user, db)
    return await artifact_review_service.latest_reviews_for_project(
        db, project_id=project_id, artifact_type=artifact_type
    )


@router.get("/artifact/{artifact_type}/{artifact_id}", response_model=list[ArtifactReviewOut])
async def get_artifact_review_history(
    artifact_type: str,
    artifact_id: int,
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(..., description="Project the artifact belongs to, for access control"),
):
    """Full review history for one artifact, newest first — feeds the findings drawer."""
    await require_project_access(project_id, current_user, db)
    return await artifact_review_service.review_history(
        db, artifact_type=artifact_type, artifact_id=artifact_id
    )


@router.get("/coverage-matrix/project/{project_id}", response_model=list[CoverageMatrixEntryOut])
async def get_coverage_matrix(
    project_id: int,
    db: DBSession,
    current_user: CurrentUser,
    requirement_id: int | None = Query(None),
    scenario_id: int | None = Query(None),
):
    await require_project_access(project_id, current_user, db)
    return await coverage_matrix_service.list_for_project(
        db, project_id=project_id, requirement_id=requirement_id, scenario_id=scenario_id
    )
