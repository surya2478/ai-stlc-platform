"""Automation Script service — CRUD operations."""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.automation_script import AutomationScript
from app.schemas.automation import AutomationScriptUpdate


async def list_scripts(
    db: AsyncSession,
    project_id: int,
    test_case_id: int | None = None,
    status: str | None = None,
) -> list[AutomationScript]:
    stmt = (
        select(AutomationScript)
        .where(AutomationScript.project_id == project_id)
        .order_by(AutomationScript.created_at.desc())
    )
    if test_case_id:
        stmt = stmt.where(AutomationScript.test_case_id == test_case_id)
    if status:
        stmt = stmt.where(AutomationScript.status == status)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_script(db: AsyncSession, script_id: int) -> AutomationScript | None:
    result = await db.execute(
        select(AutomationScript).where(AutomationScript.id == script_id)
    )
    return result.scalar_one_or_none()


async def update_script(
    db: AsyncSession, script: AutomationScript, updates: AutomationScriptUpdate
) -> AutomationScript:
    data = updates.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(script, key, value)
    await db.flush()
    await db.refresh(script)
    return script


async def approve_script(
    db: AsyncSession, script: AutomationScript, action: str, notes: str | None
) -> AutomationScript:
    script.status = "approved" if action == "approve" else "rejected"
    if notes:
        script.metadata_ = {**(script.metadata_ or {}), "review_notes": notes}
    await db.flush()
    await db.refresh(script)
    return script


async def count_scripts_by_project(db: AsyncSession, project_id: int) -> dict:
    result = await db.execute(
        select(AutomationScript.status, func.count())
        .where(AutomationScript.project_id == project_id)
        .group_by(AutomationScript.status)
    )
    return {row[0]: row[1] for row in result.all()}
