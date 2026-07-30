"""UI-020/021/023 Automation Asset Workspace endpoints — /api/v1/lab/automation-assets/*.

Isolated namespace with the same 404-when-disabled pattern as
automation_suites.py: every route 404s when AUTOMATION_SUITE_ENABLED is off,
because an automation asset only exists inside a suite.

The three tabs are one workspace over one suite member. `GET /members/{id}`
returns everything the workspace needs in a single request (contract Section
25); the remaining routes are the actions.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.api.deps import CurrentUser, DBSession, require_permission
from app.config import get_settings
from app.schemas.automation_asset import (
    AcceptExceptionRequest,
    FinalApprovalRequest,
    SaveIrRequest,
    ValidateIrRequest,
)
from app.services.automation_asset import decisions as decision_service
from app.services.automation_asset import ir_service
from app.services.automation_asset import script_service
from app.services.automation_asset import validation_service
from app.services.automation_asset import workspace_service
from app.services.rbac_service import (
    AUTOMATION_ASSET_ACCEPT_EXCEPTION,
    AUTOMATION_ASSET_COMPILE,
    AUTOMATION_ASSET_DRY_RUN,
    AUTOMATION_ASSET_EDIT_IR,
    AUTOMATION_ASSET_FINAL_APPROVE,
    AUTOMATION_ASSET_VIEW,
)

router = APIRouter()


def _require_enabled() -> None:
    if not get_settings().automation_suite_enabled:
        raise HTTPException(
            status_code=404,
            detail="Automation Workspace is disabled (AUTOMATION_SUITE_ENABLED=false)",
        )


# ─── Asset picker (the workspace's landing page) ──────────────────────────────

@router.get("/projects/{project_id}/assets")
async def list_project_assets(
    project_id: int, db: DBSession, current_user: CurrentUser
):
    """Every automation asset in the project, with both state axes.

    The workspace opens on one member, so a navigation entry needs somewhere to
    land. This is that list — and it doubles as the aging queue from contract
    Section 16: deferred human review is only safe when the backlog is a number
    on a screen rather than an invisible pile.
    """
    _require_enabled()
    await require_permission(AUTOMATION_ASSET_VIEW, project_id, current_user, db)

    from sqlalchemy import select

    from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
    from app.models.test_case import TestCase

    rows = (
        await db.execute(
            select(AutomationSuiteTestCase, AutomationSuite, TestCase)
            .join(AutomationSuite, AutomationSuite.id == AutomationSuiteTestCase.suite_id)
            .outerjoin(TestCase, TestCase.id == AutomationSuiteTestCase.test_case_id)
            .where(AutomationSuite.project_id == project_id)
            .order_by(AutomationSuite.id, AutomationSuiteTestCase.id)
        )
    ).all()

    assets = [
        {
            "member_id": member.id,
            "suite_id": suite.id,
            "suite_name": suite.name,
            "suite_status": suite.status,
            "test_case_id": member.test_case_id,
            "test_case_display_id": getattr(test_case, "test_case_id", None) if test_case else None,
            "test_case_title": getattr(test_case, "title", None) if test_case else None,
            "member_status": member.member_status,
            "inclusion_status": member.inclusion_status,
            "autonomy_state": member.autonomy_state,
            "approval_state": member.approval_state,
            "has_script": member.resolved_script_id is not None,
            "framework": member.resolved_framework,
            "last_evaluated_at": member.last_evaluated_at,
        }
        for member, suite, test_case in rows
    ]

    return {
        "assets": assets,
        "counts": {
            "total": len(assets),
            "ai_approved": sum(1 for a in assets if a["autonomy_state"] == "AI_APPROVED"),
            "ai_held": sum(1 for a in assets if a["autonomy_state"] == "AI_HELD"),
            "pending_final_approval": sum(
                1
                for a in assets
                if a["autonomy_state"] == "AI_APPROVED" and a["approval_state"] == "PENDING_FINAL"
            ),
            "final_approved": sum(1 for a in assets if a["approval_state"] == "FINAL_APPROVED"),
        },
    }


# ─── Workspace payload ────────────────────────────────────────────────────────

@router.get("/members/{member_id}")
async def get_asset(member_id: int, db: DBSession, current_user: CurrentUser):
    """The whole workspace for one suite member, in one request."""
    _require_enabled()
    _, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)
    return await workspace_service.build_asset(db, member_id)


# ─── UI-020 IR Editor ─────────────────────────────────────────────────────────

@router.get("/members/{member_id}/ir")
async def get_ir(member_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    draft = await ir_service.current_draft(db, member, suite)
    if draft is None:
        return {"ir": None, "validation": None}
    return {
        "ir": {
            "id": draft.id,
            "version": draft.version,
            "is_current": draft.is_current,
            "status": draft.status,
            "contract": draft.contract,
            "contract_version": draft.contract_version,
            "readiness": draft.readiness or {},
            "source_action_ids": list(draft.source_action_ids or []),
            "generated_by": draft.generated_by,
        },
        "validation": ir_service.validate_contract(draft.contract),
    }


@router.post("/members/{member_id}/ir/validate")
async def validate_ir(
    member_id: int, payload: ValidateIrRequest, db: DBSession, current_user: CurrentUser
):
    """Validate without saving — the live-edit endpoint (contract Section 11.4).

    Returns 200 with `valid: false` and the real pydantic messages for an
    invalid draft. A draft being invalid mid-edit is a normal state, not an
    error condition, so it must not be a 4xx: the editor needs the errors to
    render inline, and a rejected request would make every keystroke look like
    a failure.
    """
    _require_enabled()
    _, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)
    return ir_service.validate_contract(payload.contract)


@router.put("/members/{member_id}/ir")
async def save_ir(
    member_id: int, payload: SaveIrRequest, db: DBSession, current_user: CurrentUser
):
    """Persist an edited contract. Validates first; 422 with real errors if invalid."""
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_EDIT_IR, suite.project_id, current_user, db)

    if suite.status == "PUBLISHED":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUITE_IMMUTABLE",
                "message": "This suite is published and frozen. Open a new version to edit it.",
            },
        )

    draft, validation = await ir_service.save_contract(
        db,
        member,
        suite,
        payload=payload.contract,
        actor_id=current_user.id,
        resolved_readiness_kinds=payload.resolved_readiness_kinds,
    )
    # An edit changes the evidence, so the verdict is refreshed in the same
    # transaction — the workspace must never show a stale verdict beside fresh
    # behaviour.
    await decision_service.evaluate_member(db, member, suite)
    await db.commit()

    return {
        "ir": {
            "id": draft.id,
            "version": draft.version,
            "is_current": draft.is_current,
            "status": draft.status,
            "contract": draft.contract,
            "contract_version": draft.contract_version,
            "readiness": draft.readiness or {},
            "source_action_ids": list(draft.source_action_ids or []),
            "generated_by": draft.generated_by,
        },
        "validation": validation,
    }


@router.get("/members/{member_id}/ir/versions")
async def list_ir_versions(member_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    versions = await ir_service.list_versions(db, member, suite)
    other = await ir_service.count_other_session_drafts(db, member, suite)
    return {
        "versions": [
            {
                "id": v.id,
                "version": v.version,
                "is_current": v.is_current,
                "status": v.status,
                "session_id": v.session_id,
                "step_count": (v.readiness or {}).get("step_count", 0),
                "custom_step_count": (v.readiness or {}).get("custom_step_count", 0),
                "unresolved_count": (v.readiness or {}).get("unresolved_count", 0),
                "generated_by": v.generated_by,
                "created_at": v.created_at,
            }
            for v in versions
        ],
        # Not merged into the chain — see ir_service.list_versions.
        "other_session_draft_count": other,
    }


@router.get("/members/{member_id}/elements")
async def get_element_catalogue(member_id: int, db: DBSession, current_user: CurrentUser):
    """Elements the picker may offer (contract Section 11.5).

    A step target is never a text input, so this is what makes the editor
    usable: the declared list is what a target may reference today, and the
    available list is what can be added, each labelled with its source.
    """
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    draft = await ir_service.current_draft(db, member, suite)
    return await ir_service.element_catalogue(
        db,
        project_id=suite.project_id,
        application_id=member.resolved_application_id,
        draft=draft,
    )


# ─── UI-021 Script Editor ─────────────────────────────────────────────────────

@router.get("/members/{member_id}/script")
async def get_script(member_id: int, db: DBSession, current_user: CurrentUser):
    """The compiled bundle. Read-only — see contract Section 12.1.

    There is deliberately no route that accepts script source. ADR-001 makes the
    compiler the only writer of code, and `static_quality_gate` enforces it by
    hard-blocking any script missing the generation header.
    """
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    if member.resolved_script_id is None:
        return {
            "script": None,
            "unavailable": "This asset has not been compiled yet.",
            "dry_runs": [],
        }

    from app.models.automation_script import AutomationScript

    script = await db.get(AutomationScript, member.resolved_script_id)
    if script is None:
        return {
            "script": None,
            "unavailable": "The linked script row no longer exists.",
            "dry_runs": [],
        }

    history = await script_service.list_dry_runs(db, member, project_id=suite.project_id)
    return {
        "script": {
            "id": script.id,
            "script_id": script.script_id,
            "framework": script.framework,
            "version": script.version,
            "parent_script_id": script.parent_script_id,
            "status": script.status,
            "entry_path": script.file_path,
            "compiled_files": script.compiled_files or {},
            "execution_command": script.execution_command,
            "setup_required": script.setup_required or [],
            "static_gate_result": script.static_gate_result,
            "compiler_version": (script.metadata_ or {}).get("compiler_version"),
            "created_by": script.created_by,
            "updated_at": getattr(script, "updated_at", None),
        },
        "unavailable": None,
        "dry_runs": [
            {
                "id": r.id,
                "test_name": r.test_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "created_at": getattr(r, "created_at", None),
            }
            for r in history
        ],
    }


@router.post("/members/{member_id}/compile")
async def compile_asset(member_id: int, db: DBSession, current_user: CurrentUser):
    """Compile the current IR into a NEW script version. Never mutates a prior one."""
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_COMPILE, suite.project_id, current_user, db)

    if suite.status == "PUBLISHED":
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SUITE_IMMUTABLE",
                "message": "This suite is published and frozen. Open a new version to recompile.",
            },
        )

    script = await script_service.compile_asset(db, member, suite, actor_id=current_user.id)
    # Compiling changes the evidence, so the verdict is refreshed in the same
    # transaction rather than left stale beside fresh code.
    await decision_service.evaluate_member(db, member, suite)
    await db.commit()

    return {
        "script_id": script.script_id,
        "id": script.id,
        "version": script.version,
        "framework": script.framework,
        "entry_path": script.file_path,
        "file_count": len(script.compiled_files or {}),
        "status": script.status,
        "static_gate_result": script.static_gate_result,
    }


@router.post("/members/{member_id}/dry-run")
async def dry_run_asset(member_id: int, db: DBSession, current_user: CurrentUser):
    """Run the compiled script through the real runner — a subprocess, not a simulation.

    Writes `ExecutionResult` rows carrying `dry_run: true` and
    `automation_script_id`, which is the evidence autonomy precondition 4 reads.
    """
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_DRY_RUN, suite.project_id, current_user, db)

    outcome = await script_service.dry_run_asset(db, member, suite, actor_id=current_user.id)
    await decision_service.evaluate_member(db, member, suite)
    await db.commit()
    return outcome


@router.get("/runner-status")
async def get_runner_status(current_user: CurrentUser):
    """Which frameworks can actually execute here.

    Host-wide, so no project scope. Surfaced so a dry-run button can be disabled
    with the runner's real reason rather than failing on click — on a Windows
    developer host `npx` is not resolvable and every framework reports
    unavailable, which is accurate rather than a bug.
    """
    _require_enabled()
    from app.services.automation_runner.preflight import runtime_status

    return {
        "frameworks": [
            {"framework": key, "available": value.available, "detail": value.detail}
            for key, value in runtime_status().items()
        ]
    }


# ─── UI-023 Validation and Review ─────────────────────────────────────────────

@router.get("/members/{member_id}/validation")
async def get_validation(member_id: int, db: DBSession, current_user: CurrentUser):
    """Gate findings, execution evidence, readiness, score and the gating decision."""
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)
    return await validation_service.build_validation(db, member, suite)


@router.post("/members/{member_id}/validation/exceptions")
async def accept_gate_exception(
    member_id: int,
    payload: AcceptExceptionRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """Waive a gate WARNING. A governance decision, so it rides with approval."""
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(
        AUTOMATION_ASSET_ACCEPT_EXCEPTION, suite.project_id, current_user, db
    )

    result = await validation_service.accept_exception(
        db, member, suite, code=payload.code, reason=payload.reason, actor_id=current_user.id
    )
    await db.commit()
    return result


@router.post("/members/{member_id}/final-approval")
async def final_approval(
    member_id: int,
    payload: FinalApprovalRequest,
    db: DBSession,
    current_user: CurrentUser,
):
    """The one governed human gate.

    Separation of duty is enforced in the service by comparing the actor against
    the artifact's author, not by the permission — the same split UI-018 uses.
    """
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(
        AUTOMATION_ASSET_FINAL_APPROVE, suite.project_id, current_user, db
    )

    decision = await decision_service.final_approve(
        db,
        member,
        suite,
        actor_id=current_user.id,
        approve=payload.approve,
        reason=payload.reason,
    )
    await db.commit()
    return {
        "decision_id": decision.id,
        "decision": decision.decision,
        "approval_state": member.approval_state,
        "autonomy_state": member.autonomy_state,
        "decided_by": decision.decided_by,
        "threshold": decision.threshold,
        "score": float(decision.score) if decision.score is not None else None,
    }


@router.get("/suites/{suite_id}/pending-final-approval")
async def pending_final_approval(suite_id: int, db: DBSession, current_user: CurrentUser):
    """The aging queue (contract Section 16).

    Deferred human review is only safe if the backlog is visible; without this
    an AI-approved asset can sit unreviewed indefinitely.
    """
    _require_enabled()
    from app.models.automation_suite import AutomationSuite

    suite = await db.get(AutomationSuite, suite_id)
    if suite is None:
        raise HTTPException(status_code=404, detail="Automation suite not found")
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    pending = await decision_service.pending_final_approval(db, suite_id)
    lacking = await decision_service.members_lacking_final_approval(db, suite_id)
    return {
        "pending_final_approval": [
            {
                "member_id": m.id,
                "test_case_id": m.test_case_id,
                "autonomy_state": m.autonomy_state,
                "approval_state": m.approval_state,
                "last_evaluated_at": m.last_evaluated_at,
            }
            for m in pending
        ],
        "blocking_publish": [
            {
                "member_id": m.id,
                "test_case_id": m.test_case_id,
                "approval_state": m.approval_state,
            }
            for m in lacking
        ],
    }


# ─── Provenance (contract Section 11.7) ───────────────────────────────────────

@router.get("/members/{member_id}/provenance")
async def get_provenance(member_id: int, db: DBSession, current_user: CurrentUser):
    """The observed recorder actions this IR was emitted from.

    A step with no source action is labelled "authored" by the UI rather than
    left ambiguous — this endpoint returns only what genuinely exists.
    """
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    draft = await ir_service.current_draft(db, member, suite)
    if draft is None or not draft.source_action_ids:
        return {"actions": [], "unavailable": "This IR records no source actions."}

    from sqlalchemy import select

    from app.models.discovery_session import DiscoveryAction

    rows = (
        await db.execute(
            select(DiscoveryAction)
            .where(DiscoveryAction.id.in_(list(draft.source_action_ids)))
            .order_by(DiscoveryAction.id)
        )
    ).scalars().all()

    # DiscoveryAction's real fields are action_family / target_semantic /
    # target_element_ref — there is no `action_type` or `description`, and
    # reading those returned nulls that made every provenance row read
    # "Action #21" with no content.
    return {
        "actions": [
            {
                "id": a.id,
                "sequence": a.sequence,
                "actor": a.actor,
                "action_family": a.action_family,
                "target_semantic": a.target_semantic,
                "target_element_ref": a.target_element_ref,
                "target_screen_ref": a.target_screen_ref,
                "test_step_ref": a.test_step_ref,
                "created_at": getattr(a, "created_at", None),
            }
            for a in rows
        ],
        "unavailable": None,
    }


# ─── Autonomy (read + explicit re-evaluation) ─────────────────────────────────

@router.post("/members/{member_id}/evaluate")
async def evaluate_asset(member_id: int, db: DBSession, current_user: CurrentUser):
    """Recompute the autonomy verdict for this asset.

    Manual trigger; the same evaluation also runs automatically after an edit.
    """
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    verdict, decision = await decision_service.evaluate_member(db, member, suite)
    await db.commit()
    return {
        "autonomy_state": member.autonomy_state,
        "approval_state": member.approval_state,
        "decision_id": decision.id if decision else None,
        **verdict.as_dict(),
    }


@router.get("/members/{member_id}/decisions")
async def list_decisions(member_id: int, db: DBSession, current_user: CurrentUser):
    _require_enabled()
    member, suite = await workspace_service.load_member(db, member_id)
    await require_permission(AUTOMATION_ASSET_VIEW, suite.project_id, current_user, db)

    from sqlalchemy import select

    from app.models.automation_asset_decision import AutomationAssetDecision

    rows = (
        await db.execute(
            select(AutomationAssetDecision)
            .where(AutomationAssetDecision.suite_test_case_id == member.id)
            .order_by(AutomationAssetDecision.created_at.desc(), AutomationAssetDecision.id.desc())
        )
    ).scalars().all()

    return [
        {
            "id": r.id,
            "decision": r.decision,
            "decided_by": r.decided_by,
            "rubric_id": r.rubric_id,
            "threshold": r.threshold,
            "score": float(r.score) if r.score is not None else None,
            "dimensions": r.dimensions,
            "preconditions": r.preconditions,
            "model_versions": r.model_versions,
            "reason": r.reason,
            "created_at": r.created_at,
        }
        for r in rows
    ]
