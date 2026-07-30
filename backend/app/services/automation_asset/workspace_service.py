"""UI-020/021/023 — assembling the Automation Asset Workspace payload.

One request builds the whole workspace (Section 25). Inherited context is
resolved once through UI-018's `inheritance.resolve_suite_inheritance` — the
only module allowed to query for evaluation — and everything downstream is a
projection of that plus the autonomy verdict.

Every value that has no source renders as an explained dash. The `unavailable`
map carries the reason, following the pattern UI-016/017/018 established, so
the UI never has to decide whether a zero means "none" or "unknown".
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.services.automation_asset import decisions as decision_service
from app.services.automation_asset import evidence as evidence_engine
from app.services.automation_asset import ir_service
from app.services.automation_asset.autonomy import evaluate
from app.services.automation_suite import inheritance as inheritance_engine
from app.services.automation_suite.errors import AutomationSuiteError


async def load_member(
    db: AsyncSession, member_id: int
) -> tuple[AutomationSuiteTestCase, AutomationSuite]:
    member = await db.get(AutomationSuiteTestCase, member_id)
    if member is None:
        raise AutomationSuiteError(404, "MEMBER_NOT_FOUND", "Suite member not found.")
    suite = await db.get(AutomationSuite, member.suite_id)
    if suite is None:
        raise AutomationSuiteError(404, "SUITE_NOT_FOUND", "Automation suite not found.")
    return member, suite


def _inherited(value: str | None, source: str | None, reason: str | None = None) -> dict:
    if value:
        return {"value": value, "source": source, "available": True, "reason": None}
    return {
        "value": None,
        "source": None,
        "available": False,
        "reason": reason or "No source resolved this value.",
    }


def _readiness_strip(
    *,
    ir_validation: dict | None,
    has_ir: bool,
    has_script: bool,
    autonomy: dict,
    approval_state: str,
    suite_status: str,
) -> dict:
    """Section 10 — one message, one primary action, in plain English.

    The order of these branches is the pipeline order, so the strip always
    names the earliest thing standing in the way rather than the most severe.
    """
    if suite_status == "PUBLISHED":
        return {
            "state": "published",
            "message": "This suite is published and frozen. The asset is read-only.",
            "primary_action": None,
            "primary_action_target": None,
        }
    if not has_ir:
        return {
            "state": "no_ir",
            "message": "No Automation IR yet. Record this test case to produce one.",
            "primary_action": "Open Live Recorder",
            "primary_action_target": "recorder",
        }
    if ir_validation and not ir_validation["valid"]:
        n = len(ir_validation["errors"])
        return {
            "state": "ir_invalid",
            "message": f"{n} validation error{'s' if n != 1 else ''} in the behaviour.",
            "primary_action": f"Fix {n} error{'s' if n != 1 else ''}",
            "primary_action_target": "ir",
        }

    summary = (ir_validation or {}).get("summary") or {}
    custom = summary.get("custom_step_count", 0)
    if custom:
        return {
            "state": "ir_incomplete",
            "message": f"{custom} step{'s' if custom != 1 else ''} need a locator "
            "before this can be automated.",
            "primary_action": f"Resolve {custom} step{'s' if custom != 1 else ''}",
            "primary_action_target": "ir",
        }

    if not has_script:
        return {
            "state": "ir_ready",
            "message": "Behaviour is complete and validated.",
            "primary_action": "Compile and dry run",
            "primary_action_target": "script",
        }

    if approval_state == "FINAL_APPROVED":
        return {
            "state": "final_approved",
            "message": "Final approved. Ready to publish with the suite.",
            "primary_action": None,
            "primary_action_target": None,
        }
    if approval_state == "REJECTED":
        return {
            "state": "rejected",
            "message": "Rejected in review. Edit the behaviour and resubmit.",
            "primary_action": "Edit behaviour",
            "primary_action_target": "ir",
        }
    if autonomy["autonomy_state"] == "AI_APPROVED":
        return {
            "state": "ai_approved",
            "message": f"AI Approved at {autonomy['score']:g}/100. "
            "Awaiting final approval before publish.",
            "primary_action": "Give final approval",
            "primary_action_target": "validation",
        }
    return {
        "state": "ai_held",
        "message": autonomy.get("held_reason") or "Held pending validation.",
        "primary_action": "Review findings",
        "primary_action_target": "validation",
    }


def _tabs(*, has_ir: bool, has_script: bool) -> dict:
    """Section 6 — a tab not yet reachable is disabled with its reason, never hidden."""
    return {
        "ir": {"enabled": True, "reason": None},
        "script": {
            "enabled": has_script or has_ir,
            "reason": None
            if (has_script or has_ir)
            else "No Automation IR yet — there is nothing to compile.",
        },
        "validation": {
            "enabled": has_script,
            "reason": None if has_script else "Compile the asset before it can be validated.",
        },
    }


async def build_asset(db: AsyncSession, member_id: int) -> dict:
    """The whole workspace, in one pass."""
    member, suite = await load_member(db, member_id)

    suite_inh = await inheritance_engine.resolve_suite_inheritance(
        db, suite=suite, members=[member]
    )
    member_inh = suite_inh.members[0] if suite_inh.members else None

    asset_evidence, draft, script = await evidence_engine.gather(db, member, suite)
    policy = decision_service.policy_from_settings()
    verdict = evaluate(asset_evidence, policy)

    # The contract this asset is described by, resolved exactly as evidence.py
    # resolves it. Both must agree: an earlier version of this module used only
    # the IR draft while the autonomy policy fell back to the script's contract,
    # so the workspace said "no IR yet" beside a verdict asserting the behaviour
    # was complete. One resolution, three possible sources, always named.
    if draft is not None and draft.contract:
        contract, contract_source = draft.contract, "ir_draft"
    elif script is not None and script.contract:
        contract, contract_source = script.contract, "compiled_script"
    else:
        contract, contract_source = None, None

    ir_validation = ir_service.validate_contract(contract) if contract else None

    test_case = member_inh.test_case if member_inh else None
    application = member_inh.application if member_inh else None

    unavailable: dict[str, str] = {}

    framework_value = member.resolved_framework
    framework_source = (
        f"Derived from linked script framework '{framework_value}'" if framework_value else None
    )
    if not framework_value:
        unavailable["framework"] = (
            "No automation script is linked to this member, so no framework resolves."
        )
    # No framework_profile table exists (UI-022, P2-S3) — the plain string is
    # shown, sourced to the script, exactly as UI-018 does.
    unavailable["framework_profile"] = (
        "Framework profiles are not modelled yet (UI-022, P2-S3); the script's "
        "framework string is shown instead."
    )

    header = {
        "member_id": member.id,
        "suite_id": suite.id,
        "suite_name": suite.name,
        "suite_version": suite.version,
        "suite_status": suite.status,
        "test_case_id": member.test_case_id,
        # TestCase's human-facing identifier is `test_case_id` (a string like
        # "TC-0008"), not `display_id` — that attribute does not exist and
        # silently returned None.
        "test_case_display_id": getattr(test_case, "test_case_id", None) if test_case else None,
        "test_case_title": getattr(test_case, "title", None) if test_case else None,
        "requirement_id": getattr(test_case, "requirement_id", None) if test_case else None,
        "requirement_display_id": None,
        "application": _inherited(
            getattr(application, "name", None) if application else None,
            "Inherited from the test case's application"
            if application
            else None,
            "No application resolved for this test case.",
        ),
        "framework": _inherited(
            framework_value, framework_source, unavailable.get("framework")
        ),
        "environment": _inherited(
            member.resolved_environment,
            "Suite default environment"
            if (member_inh and member_inh.environment_source == "suite_default")
            else None,
            "The suite has no default environment set.",
        ),
        "member_status": member.member_status,
    }

    # The Behaviour panel (Section 5 rule 1): the test case is the source of
    # truth and its steps are read at render time, never copied into the IR.
    behaviour = {
        "preconditions": (test_case.preconditions if test_case else None) or [],
        "steps": (test_case.steps if test_case else None) or [],
        "expected_result": getattr(test_case, "expected_result", None) if test_case else None,
    }
    if not behaviour["steps"]:
        unavailable["behaviour"] = "This test case records no steps."

    autonomy = {
        "autonomy_state": member.autonomy_state,
        "approval_state": member.approval_state,
        "verdict_state": verdict.state,
        "score": verdict.score,
        "threshold": verdict.threshold,
        "rubric_id": verdict.rubric_id,
        "held_reason": verdict.held_reason,
        "would_approve": verdict.would_approve,
        "enabled": policy.enabled,
        "dimensions": verdict.dimensions,
        "preconditions": [p.as_dict() for p in verdict.preconditions],
    }
    if verdict.score is None:
        unavailable["score"] = (
            "No automation script is linked yet, so a confidence score cannot be computed."
        )

    ir_payload = None
    if draft is not None:
        ir_payload = {
            "id": draft.id,
            "version": draft.version,
            "is_current": draft.is_current,
            "status": draft.status,
            "contract": draft.contract,
            "contract_version": draft.contract_version,
            "readiness": draft.readiness or {},
            "source_action_ids": list(draft.source_action_ids or []),
            "generated_by": draft.generated_by,
            "updated_at": getattr(draft, "updated_at", None),
            "source": "ir_draft",
            "editable": True,
        }
    elif contract_source == "compiled_script":
        # A real and common case: an asset generated before the Live Recorder
        # existed has a validated contract on its script but no draft row. It is
        # shown read-only rather than pretended away, because editing it would
        # need a draft that does not exist. Creating one is a deliberate act,
        # not a side effect of opening the tab.
        ir_payload = {
            "id": None,
            "version": script.version,
            "is_current": True,
            "status": "FROM_SCRIPT",
            "contract": contract,
            "contract_version": (contract or {}).get("contractVersion", "1.0"),
            "readiness": {},
            "source_action_ids": [],
            "generated_by": script.created_by,
            "updated_at": None,
            "source": "compiled_script",
            "editable": False,
        }
        unavailable["ir_draft"] = (
            "This asset's behaviour comes from the contract stored on its compiled "
            "script, not from a recorded IR draft, so it is read-only here. Record "
            "the test case in the Live Recorder to open an editable draft."
        )
    else:
        unavailable["ir"] = (
            "No Automation IR exists for this asset. Record the test case in the "
            "Live Recorder to produce one."
        )

    script_payload = None
    if script is not None:
        script_payload = {
            "id": script.id,
            "script_id": script.script_id,
            "framework": script.framework,
            "version": script.version,
            "status": script.status,
            "entry_path": script.file_path,
            "file_count": len(script.compiled_files or {}),
            "static_gate_result": script.static_gate_result,
        }
    else:
        unavailable["script"] = "This asset has not been compiled yet."

    return {
        "header": header,
        "behaviour": behaviour,
        "readiness_strip": _readiness_strip(
            ir_validation=ir_validation,
            has_ir=contract is not None,
            has_script=script is not None,
            autonomy=autonomy,
            approval_state=member.approval_state,
            suite_status=suite.status,
        ),
        "tabs": _tabs(has_ir=contract is not None, has_script=script is not None),
        "ir": ir_payload,
        "ir_validation": ir_validation,
        "autonomy": autonomy,
        "script": script_payload,
        "unavailable": unavailable,
    }
