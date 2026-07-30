"""UI-023 Validation and Review — assembling the verdict and accepting exceptions.

This module presents; it does not judge. Every value comes from a decision some
other subsystem already made:

  static quality  -> `AutomationScript.static_gate_result` (persisted at compile)
  real execution  -> `ExecutionResult` rows with `dry_run: true`
  readiness       -> the IR emitter's readiness map
  confidence      -> `automation_confidence_service`
  gating decision -> `automation_asset.autonomy`

Recomputing any of them here would create a second opinion, and the whole point
of the screen is that the machine's verdict and the reviewer's evidence are the
same facts.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.automation_script import AutomationScript
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.services.automation_asset import decisions as decision_service
from app.services.automation_asset import evidence as evidence_engine
from app.services.automation_asset import script_service
from app.services.automation_asset.autonomy import evaluate
from app.services.automation_suite.errors import AutomationSuiteError

# Gate findings a reviewer may waive. Blocking violations are deliberately NOT
# waivable from this screen (contract Section 13.4) — clearing a hard block is
# a change to the asset, not a review decision about it.
WAIVABLE_SEVERITY = "warn"


def _card(label: str, status: str, detail: str, *, available: bool = True, reason: str | None = None) -> dict:
    return {
        "label": label,
        "status": status,
        "detail": detail,
        "available": available,
        "reason": reason,
    }


async def build_validation(
    db: AsyncSession, member: AutomationSuiteTestCase, suite: AutomationSuite
) -> dict:
    """The whole Validation & Review payload for one member."""
    asset_evidence, draft, script = await evidence_engine.gather(db, member, suite)
    policy = decision_service.policy_from_settings()
    verdict = evaluate(asset_evidence, policy)

    gate = (script.static_gate_result if script else None) or None
    violations = (gate or {}).get("violations") or []
    warnings = (gate or {}).get("warnings") or []
    accepted = set(((script.metadata_ or {}).get("static_gate_exceptions") or []) if script else [])

    unavailable: dict[str, str] = {}

    # ── The four summary cards ───────────────────────────────────────────────
    if gate is None:
        static_card = _card(
            "Static quality", "unknown", "—",
            available=False,
            reason="This asset has not been compiled, so the gate has not run.",
        )
        unavailable["static_quality"] = static_card["reason"]
    else:
        static_card = _card(
            "Static quality",
            "pass" if gate.get("passed") else "fail",
            f"{len(violations)} critical · {len(warnings)} minor",
        )

    if asset_evidence.total_dry_runs == 0:
        execution_card = _card(
            "Real execution", "unknown", "—",
            available=False,
            reason="This asset has never been executed.",
        )
        unavailable["real_execution"] = execution_card["reason"]
    else:
        execution_card = _card(
            "Real execution",
            "pass" if asset_evidence.passing_dry_runs == asset_evidence.total_dry_runs else "fail",
            f"{asset_evidence.passing_dry_runs} of {asset_evidence.total_dry_runs} passed",
        )

    readiness = (draft.readiness if draft else None) or {}
    unresolved = readiness.get("unresolved") or []
    if draft is None:
        readiness_card = _card(
            "Readiness", "unknown", "—",
            available=False,
            reason="No Automation IR draft exists, so there is no readiness map.",
        )
        unavailable["readiness"] = readiness_card["reason"]
    else:
        readiness_card = _card(
            "Readiness",
            "pass" if not unresolved else "partial",
            "Nothing unresolved" if not unresolved else f"{len(unresolved)} unresolved",
        )

    if verdict.score is None:
        score_card = _card(
            "Confidence score", "unknown", "—",
            available=False,
            reason="No compiled script, so a confidence score cannot be computed.",
        )
        unavailable["confidence_score"] = score_card["reason"]
    else:
        score_card = _card(
            "Confidence score",
            "pass" if verdict.score >= policy.threshold else "below",
            f"{verdict.score:g} / 100",
        )

    # ── Validation details ───────────────────────────────────────────────────
    findings = [
        {
            "code": v["code"],
            "message": v["message"],
            "severity": "block",
            "waivable": False,
            "accepted": False,
        }
        for v in violations
    ] + [
        {
            "code": w["code"],
            "message": w["message"],
            "severity": "warn",
            "waivable": True,
            "accepted": w["code"] in accepted,
        }
        for w in warnings
    ]

    dry_runs = await script_service.list_dry_runs(db, member, project_id=suite.project_id)

    return {
        "cards": {
            "static_quality": static_card,
            "real_execution": execution_card,
            "readiness": readiness_card,
            "confidence_score": score_card,
        },
        "gating": {
            **verdict.as_dict(),
            "autonomy_state": member.autonomy_state,
            "approval_state": member.approval_state,
            "enabled": policy.enabled,
        },
        "findings": findings,
        # Rendered as its own row so a skipped check is visible rather than
        # absent — it is never coloured as a pass (contract Section 13.3).
        "syntax_check": {
            "status": (gate or {}).get("syntax_check", "skipped"),
            "detail": (gate or {}).get("syntax_check_detail"),
        },
        "readiness_items": unresolved,
        "dry_runs": [
            {
                "id": r.id,
                "test_name": r.test_name,
                "status": r.status,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "created_at": getattr(r, "created_at", None),
            }
            for r in dry_runs
        ],
        "accepted_exceptions": sorted(accepted),
        "script_id": script.script_id if script else None,
        "unavailable": unavailable,
    }


async def accept_exception(
    db: AsyncSession,
    member: AutomationSuiteTestCase,
    suite: AutomationSuite,
    *,
    code: str,
    reason: str,
    actor_id: int,
) -> dict:
    """Waive a gate WARNING for this script.

    Appends to `metadata_["static_gate_exceptions"]`, the mechanism
    `static_quality_gate` already honours — an exempted kind never blocks and
    only warns. Blocking violations cannot be waived here: that would let a
    review decision clear a hard failure the gate exists to enforce.
    """
    if not (reason or "").strip():
        raise AutomationSuiteError(
            422, "REASON_REQUIRED", "Accepting a gate finding as an exception requires a reason."
        )
    if member.resolved_script_id is None:
        raise AutomationSuiteError(409, "NOT_COMPILED", "This asset has not been compiled.")

    script = await db.get(AutomationScript, member.resolved_script_id)
    if script is None:
        raise AutomationSuiteError(404, "SCRIPT_NOT_FOUND", "The compiled script is missing.")

    gate = script.static_gate_result or {}
    blocking_codes = {v["code"] for v in (gate.get("violations") or [])}
    warning_codes = {w["code"] for w in (gate.get("warnings") or [])}

    if code in blocking_codes:
        raise AutomationSuiteError(
            409,
            "NOT_WAIVABLE",
            f"'{code}' is a blocking violation and cannot be accepted as an exception. "
            "Fix the behaviour and recompile.",
        )
    if code not in warning_codes:
        raise AutomationSuiteError(
            404, "FINDING_NOT_FOUND", f"'{code}' is not an open warning on this script."
        )

    metadata = dict(script.metadata_ or {})
    existing = list(metadata.get("static_gate_exceptions") or [])
    if code not in existing:
        existing.append(code)
    metadata["static_gate_exceptions"] = existing
    # Who waived what and why — the gate itself only stores the code, so the
    # accountability lives alongside it.
    log = list(metadata.get("static_gate_exception_log") or [])
    log.append({"code": code, "reason": reason, "actor_id": actor_id})
    metadata["static_gate_exception_log"] = log
    script.metadata_ = metadata

    # Re-run the gate so the persisted verdict reflects the waiver immediately.
    from app.services import static_quality_gate

    result = static_quality_gate.run_static_quality_gate(script)
    script.static_gate_result = result.as_dict()
    await db.flush()

    await decision_service.evaluate_member(db, member, suite)
    return result.as_dict()
