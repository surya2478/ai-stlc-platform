"""Screen 3: script generation, editing and packaging."""
from __future__ import annotations

import io
import re
import zipfile

from fastapi import HTTPException, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.test_automation_studio.script_agent import ScriptGenerationAgent
from app.config import get_settings
from app.models.test_automation_studio import TasRefinedTestCase, TasScriptAsset
from app.schemas.test_automation_studio import (
    FRAMEWORK_LANGUAGES,
    SUPPORTED_FRAMEWORKS,
    DeletionSummary,
    GenerateScriptsRequest,
    ScriptAssetUpdate,
)
from app.services import agent_run_service
from app.services.test_automation_studio.progress import ProgressCallback
from app.services.test_automation_studio.progress import report as _report

settings = get_settings()

FRAMEWORK_EXTENSIONS = {
    "playwright": ".spec.ts",
    "katalon": ".groovy",
    "appium": ".py",
}


def _safe_slug(value: str) -> str:
    """Filesystem-safe name for a downloaded script.

    Applied to values that end up as paths inside a zip, so it strips path
    separators and traversal sequences rather than only spaces.
    """
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", (value or "").strip())
    cleaned = cleaned.replace("..", "_").strip("._")
    return cleaned or "script"


def _script_filename(test_case: TasRefinedTestCase, framework: str) -> str:
    extension = FRAMEWORK_EXTENSIONS.get(framework, ".txt")
    if framework == "appium":
        return f"test_{_safe_slug(test_case.tc_display_id).lower()}{extension}"
    return f"{_safe_slug(test_case.tc_display_id)}{extension}"


def _test_case_payload(test_case: TasRefinedTestCase) -> dict:
    return {
        "tc_display_id": test_case.tc_display_id,
        "title": test_case.title,
        "objective": test_case.objective,
        "preconditions": test_case.preconditions or [],
        "steps": test_case.steps or [],
        "expected_result": test_case.expected_result,
        "application_url": test_case.application_url,
        "priority": test_case.priority,
        "test_type": test_case.test_type,
        "test_data_requirements": test_case.test_data_requirements or [],
    }


async def validate_generation_request(
    db: AsyncSession, *, project_id: int, body: GenerateScriptsRequest
) -> None:
    """Request-time checks, so a doomed job is refused before it is queued."""
    if body.framework not in SUPPORTED_FRAMEWORKS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported framework. Supported: {', '.join(SUPPORTED_FRAMEWORKS)}.",
        )
    found = (
        await db.execute(
            select(func.count(TasRefinedTestCase.id)).where(
                TasRefinedTestCase.id.in_(body.test_case_ids),
                TasRefinedTestCase.project_id == project_id,
            )
        )
    ).scalar_one()
    if not found:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested test cases were found in this project",
        )
    if found > settings.tas_max_test_cases_per_run:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{found} test cases selected, over the "
                f"{settings.tas_max_test_cases_per_run} limit for one run."
            ),
        )


async def generate_scripts(
    db: AsyncSession,
    *,
    project_id: int,
    body: GenerateScriptsRequest,
    user_id: int,
    run=None,
    on_progress: ProgressCallback | None = None,
) -> tuple[list[TasScriptAsset], list[dict], int | None]:
    if body.framework not in SUPPORTED_FRAMEWORKS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unsupported framework. Supported: {', '.join(SUPPORTED_FRAMEWORKS)}.",
        )

    test_cases = list(
        (
            await db.execute(
                select(TasRefinedTestCase).where(
                    TasRefinedTestCase.id.in_(body.test_case_ids),
                    TasRefinedTestCase.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    if not test_cases:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="None of the requested test cases were found in this project",
        )

    generated: list[TasScriptAsset] = []
    skipped: list[dict] = []
    eligible: list[TasRefinedTestCase] = []

    for test_case in test_cases:
        # Screen 3's contract is "all approved TCs land here". Generating from
        # an unapproved one would produce a script for content still being
        # edited, and generating from a manual one would produce a script for
        # something the project has decided a human must run.
        if test_case.status != "approved":
            skipped.append(
                {
                    "test_case_id": test_case.id,
                    "tc_display_id": test_case.tc_display_id,
                    "reason": "Only approved test cases can have scripts generated.",
                }
            )
            continue
        if test_case.classification != "automation":
            skipped.append(
                {
                    "test_case_id": test_case.id,
                    "tc_display_id": test_case.tc_display_id,
                    "reason": f"Classified '{test_case.classification}', not 'automation'.",
                }
            )
            continue
        eligible.append(test_case)

    if not eligible:
        return [], skipped, None

    if len(eligible) > settings.tas_max_test_cases_per_run:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"This selection would generate {len(eligible)} scripts, over the "
                f"{settings.tas_max_test_cases_per_run} limit for one run."
            ),
        )

    if run is None:
        # Direct call rather than a worker dispatch — still recorded, so the
        # audit trail does not depend on which path invoked the work.
        run = await agent_run_service.start_agent_run(
            db,
            project_id=project_id,
            user_id=user_id,
            agent_name="tas_script_generation",
            input_data={
                "framework": body.framework,
                "test_case_ids": [tc.id for tc in eligible],
            },
        )

    agent = ScriptGenerationAgent()
    total = len(eligible)

    for index, test_case in enumerate(eligible):
        # Real per-item progress: one script is one LLM call, so "4 of 11" is a
        # fact rather than an animation.
        await _report(
            on_progress,
            # 10..95, leaving room for the queued state below and the commit above.
            10 + int((index / total) * 85),
            f"Generating {body.framework} script {index + 1} of {total} ({test_case.tc_display_id})",
        )
        existing = (
            await db.execute(
                select(TasScriptAsset)
                .where(
                    TasScriptAsset.refined_test_case_id == test_case.id,
                    TasScriptAsset.framework == body.framework,
                )
                .order_by(TasScriptAsset.version.desc())
                .limit(1)
            )
        ).scalars().first()

        if existing is not None and not body.regenerate:
            skipped.append(
                {
                    "test_case_id": test_case.id,
                    "tc_display_id": test_case.tc_display_id,
                    "reason": "A script already exists - pass regenerate=true to create a new version.",
                }
            )
            continue

        result = await agent.run(test_case=_test_case_payload(test_case), framework=body.framework)
        if not result.success:
            skipped.append(
                {
                    "test_case_id": test_case.id,
                    "tc_display_id": test_case.tc_display_id,
                    "reason": result.error or "Script generation failed.",
                }
            )
            continue

        version = (existing.version + 1) if existing is not None else 1
        if existing is not None:
            existing.is_current = False
            db.add(existing)

        asset = TasScriptAsset(
            project_id=project_id,
            refined_test_case_id=test_case.id,
            framework=body.framework,
            language=FRAMEWORK_LANGUAGES.get(body.framework, "text"),
            script_key=_script_filename(test_case, body.framework),
            code=result.data["code"],
            files=result.data.get("files") or {},
            execution_command=result.data.get("execution_command"),
            setup_notes=result.data.get("setup_notes") or [],
            status="draft",
            version=version,
            is_current=True,
            agent_run_id=run.id,
            created_by=user_id,
            updated_by=user_id,
        )
        db.add(asset)
        generated.append(asset)

    await agent_run_service.complete_agent_run(
        db,
        run,
        # The skipped entries, not just how many: "TC-0021: classified manual"
        # is the whole reason the user cares, and the run's output_data is the
        # only place the UI can read it once the job is over.
        output_data={"generated": len(generated), "skipped": skipped},
    )
    await db.commit()
    for asset in generated:
        await db.refresh(asset)
    return generated, skipped, run.id


async def list_scripts(
    db: AsyncSession,
    *,
    project_id: int,
    framework: str | None = None,
    test_case_id: int | None = None,
    current_only: bool = True,
) -> list[tuple[TasScriptAsset, TasRefinedTestCase]]:
    query = (
        select(TasScriptAsset, TasRefinedTestCase)
        .join(TasRefinedTestCase, TasScriptAsset.refined_test_case_id == TasRefinedTestCase.id)
        .where(TasScriptAsset.project_id == project_id)
    )
    if current_only:
        query = query.where(TasScriptAsset.is_current.is_(True))
    if framework:
        query = query.where(TasScriptAsset.framework == framework)
    if test_case_id is not None:
        query = query.where(TasScriptAsset.refined_test_case_id == test_case_id)
    query = query.order_by(TasRefinedTestCase.tc_display_id.asc(), TasScriptAsset.framework.asc())
    return [(asset, tc) for asset, tc in (await db.execute(query)).all()]


async def get_script_or_404(db: AsyncSession, script_id: int) -> TasScriptAsset:
    asset = await db.get(TasScriptAsset, script_id)
    if asset is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Script not found")
    return asset


async def update_script(
    db: AsyncSession, *, asset: TasScriptAsset, body: ScriptAssetUpdate, user_id: int
) -> TasScriptAsset:
    if asset.status == "approved":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An approved script cannot be edited. Reopen it first.",
        )
    updates = body.model_dump(exclude_unset=True)
    if "code" in updates and not str(updates["code"] or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Script code cannot be empty"
        )
    for field, value in updates.items():
        setattr(asset, field, value)
    asset.edited_by_user = True
    asset.status = "edited"
    asset.updated_by = user_id
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def decide_script(
    db: AsyncSession, *, asset: TasScriptAsset, decision: str, user_id: int
) -> TasScriptAsset:
    asset.status = "approved" if decision == "approve" else "draft"
    asset.updated_by = user_id
    db.add(asset)
    await db.commit()
    await db.refresh(asset)
    return asset


async def delete_scripts(
    db: AsyncSession, *, project_id: int, script_ids: list[int]
) -> DeletionSummary:
    """Remove generated scripts, version history included.

    A script is one (test case, framework) artefact; its earlier versions are
    superseded rows of the same thing and only the current one is listed.
    Deleting the current version alone would hide the artefact while leaving
    the history, and the next generation run would continue numbering from it
    rather than starting again at v1. The refined test case is untouched, so
    the script can simply be generated again.
    """
    rows = list(
        (
            await db.execute(
                select(TasScriptAsset).where(
                    TasScriptAsset.id.in_(script_ids),
                    TasScriptAsset.project_id == project_id,
                )
            )
        )
        .scalars()
        .all()
    )
    found_ids = {row.id for row in rows}
    not_found = [sid for sid in script_ids if sid not in found_ids]
    if not rows:
        return DeletionSummary(not_found=not_found)

    keys = {(row.refined_test_case_id, row.framework) for row in rows}
    every_version = list(
        (
            await db.execute(
                select(TasScriptAsset).where(
                    TasScriptAsset.project_id == project_id,
                    or_(
                        *[
                            and_(
                                TasScriptAsset.refined_test_case_id == test_case_id,
                                TasScriptAsset.framework == framework,
                            )
                            for test_case_id, framework in keys
                        ]
                    ),
                )
            )
        )
        .scalars()
        .all()
    )
    doomed_ids = [row.id for row in every_version]
    approved_deleted = sum(1 for row in every_version if row.status == "approved")

    await db.execute(
        sql_delete(TasScriptAsset)
        .where(TasScriptAsset.id.in_(doomed_ids))
        .execution_options(synchronize_session=False)
    )
    await db.commit()

    return DeletionSummary(
        deleted=sorted(found_ids),
        not_found=not_found,
        versions_deleted=len(doomed_ids) - len(found_ids),
        approved_deleted=approved_deleted,
    )


def build_zip(pairs: list[tuple[TasScriptAsset, TasRefinedTestCase]]) -> bytes:
    """Package scripts as a zip, one folder per framework."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        manifest: list[str] = ["framework,test_case_id,title,file,execution_command"]
        for asset, test_case in pairs:
            folder = _safe_slug(asset.framework)
            primary = f"{folder}/{_safe_slug(asset.script_key)}"
            archive.writestr(primary, asset.code)
            for path, contents in (asset.files or {}).items():
                safe_path = "/".join(_safe_slug(part) for part in str(path).split("/") if part)
                if safe_path:
                    archive.writestr(f"{folder}/{safe_path}", str(contents))
            if asset.setup_notes:
                archive.writestr(
                    f"{folder}/{_safe_slug(test_case.tc_display_id)}.SETUP.md",
                    "# Setup required\n\n"
                    + "\n".join(f"- {note}" for note in asset.setup_notes),
                )
            manifest.append(
                ",".join(
                    '"' + str(value or "").replace('"', '""') + '"'
                    for value in (
                        asset.framework,
                        test_case.tc_display_id,
                        test_case.title,
                        primary,
                        asset.execution_command,
                    )
                )
            )
        archive.writestr("MANIFEST.csv", "\n".join(manifest))
    return buffer.getvalue()
