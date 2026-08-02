"""UI-016 Application Model — Phase 1 build + governance service.

`build_or_rebuild_draft` is pure DB aggregation over a completed
`DiscoverySession`'s actions (no external tool call), so it runs
synchronously on the request path rather than via Celery, unlike discovery
capture. It walks `DiscoveryAction.target_screen_ref` /
`target_component_ref` / `target_element_ref` — the only structured signal a
completed session currently produces — to build Screen/Component/Element
nodes, CONTAINS/NAVIGATES_TO edges and locator evidence, and computes
deterministic gaps. See `app.models.application_model` for the version-chain
and immutability rules, and the approved UI-016 Phase 1 implementation plan
for why Journey/API/External System nodes are out of scope here.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import AgentRun
from app.models.application_model import (
    ApplicationModel,
    ApplicationModelActivity,
    ApplicationModelEdge,
    ApplicationModelGap,
    ApplicationModelLocatorEvidence,
    ApplicationModelNode,
)
from app.config import get_settings
from app.models.discovery_session import DiscoveryAction, DiscoverySession
from app.models.project_application import ProjectApplication

MUTABLE_STATUSES = {"draft", "pending_review", "changes_requested"}
LOW_CONFIDENCE_THRESHOLD = 60


class ApplicationModelError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


async def get_model_or_404(db: AsyncSession, model_id: int) -> ApplicationModel:
    row = await db.get(ApplicationModel, model_id)
    if row is None:
        raise ApplicationModelError(404, "MODEL_NOT_FOUND", "Application model not found.")
    return row


async def get_current_model(db: AsyncSession, *, project_id: int, application_id: int) -> ApplicationModel | None:
    result = await db.execute(
        select(ApplicationModel).where(
            ApplicationModel.project_id == project_id,
            ApplicationModel.application_id == application_id,
            ApplicationModel.is_current.is_(True),
        )
    )
    return result.scalars().first()


async def list_models(db: AsyncSession, *, project_id: int, application_id: int) -> list[ApplicationModel]:
    result = await db.execute(
        select(ApplicationModel)
        .where(ApplicationModel.project_id == project_id, ApplicationModel.application_id == application_id)
        .order_by(ApplicationModel.version.desc())
    )
    return list(result.scalars().all())


def _require_mutable(model: ApplicationModel) -> None:
    if model.status not in MUTABLE_STATUSES:
        raise ApplicationModelError(
            409, "MODEL_IMMUTABLE", f"Model version {model.version} is '{model.status}' and cannot be edited."
        )


async def _log_activity(
    db: AsyncSession, *, model: ApplicationModel, event_type: str, actor_id: int | None,
    node_id: int | None = None, old_value: dict | None = None, new_value: dict | None = None,
    reason: str | None = None,
) -> None:
    db.add(
        ApplicationModelActivity(
            project_id=model.project_id, model_id=model.id, event_type=event_type, actor_id=actor_id,
            node_id=node_id, old_value=old_value, new_value=new_value, reason=reason,
            correlation_id=model.correlation_id,
        )
    )
    await db.flush()


async def _upsert_node(
    db: AsyncSession, *, model_id: int, node_type: str, external_ref: str, display_name: str,
    parent_node_id: int | None, existing: dict[tuple[str, str], ApplicationModelNode],
) -> ApplicationModelNode:
    key = (node_type, external_ref)
    node = existing.get(key)
    if node is not None:
        return node
    node = ApplicationModelNode(
        model_id=model_id, node_type=node_type, external_ref=external_ref, display_name=display_name,
        parent_node_id=parent_node_id, state="DISCOVERED",
    )
    db.add(node)
    await db.flush()
    existing[key] = node
    return node


async def build_or_rebuild_draft(
    db: AsyncSession, *, project_id: int, application_id: int, session_id: int, actor_id: int,
) -> ApplicationModel:
    application = await db.get(ProjectApplication, application_id)
    if application is None or application.project_id != project_id:
        raise ApplicationModelError(404, "APPLICATION_NOT_FOUND", "Application not found in this project.")

    session = await db.get(DiscoverySession, session_id)
    if session is None or session.project_id != project_id or session.application_id != application_id:
        raise ApplicationModelError(404, "SESSION_NOT_FOUND", "Discovery session not found for this application.")
    if session.status != "COMPLETED":
        raise ApplicationModelError(
            409, "SESSION_NOT_COMPLETED", "Only a completed discovery session can be built into a model."
        )

    result = await db.execute(
        select(DiscoveryAction).where(DiscoveryAction.session_id == session_id).order_by(DiscoveryAction.sequence)
    )
    actions = list(result.scalars().all())

    head = await get_current_model(db, project_id=project_id, application_id=application_id)

    if head is not None and head.status in MUTABLE_STATUSES:
        model = head
        # Rebuilding in place — clear the previous walk's derived rows so a
        # rebuild reflects the current session state exactly, not a merge.
        await db.refresh(model, attribute_names=["nodes", "gaps"])
        for existing_node in list(model.nodes):
            await db.delete(existing_node)
        for existing_gap in list(model.gaps):
            await db.delete(existing_gap)
        await db.flush()
        event_type = "model_rebuilt"
    else:
        model = ApplicationModel(
            project_id=project_id, application_id=application_id, source_session_id=session_id,
            version=(head.version + 1) if head else 1, parent_model_id=head.id if head else None,
            is_current=True, status="draft",
        )
        if head is not None:
            head.is_current = False
        db.add(model)
        await db.flush()
        event_type = "model_built"

    model.source_session_id = session_id
    model.built_by = actor_id
    model.built_at = datetime.now(timezone.utc)
    model.built_from_action_count = len(actions)
    if model.agent_run_id is None:
        agent_run = AgentRun(
            project_id=project_id, triggered_by=actor_id, agent_name="application_model_builder",
            status="completed", input_data={"session_id": session_id, "application_id": application_id},
        )
        db.add(agent_run)
        await db.flush()
        model.agent_run_id = agent_run.id

    nodes_by_key: dict[tuple[str, str], ApplicationModelNode] = {}
    edges_seen: set[tuple[str, int, int]] = set()
    element_parent_seen: dict[str, int] = {}
    previous_screen_node: ApplicationModelNode | None = None
    gaps: list[dict[str, Any]] = []

    async def add_edge(edge_type: str, from_node: ApplicationModelNode, to_node: ApplicationModelNode) -> None:
        key = (edge_type, from_node.id, to_node.id)
        if key in edges_seen:
            return
        edges_seen.add(key)
        db.add(ApplicationModelEdge(model_id=model.id, edge_type=edge_type, from_node_id=from_node.id, to_node_id=to_node.id))

    for action in actions:
        screen_node = None
        if action.target_screen_ref:
            screen_node = await _upsert_node(
                db, model_id=model.id, node_type="screen", external_ref=action.target_screen_ref,
                display_name=action.target_screen_ref, parent_node_id=None, existing=nodes_by_key,
            )
        elif action.target_component_ref or action.target_element_ref:
            gaps.append({
                "gap_type": "MISSING_SCREEN", "severity": "critical",
                "evidence": {"action_id": action.id, "sequence": action.sequence},
                "remediation": "Correct this action's screen reference in Live Discovery Session and rebuild.",
            })

        component_node = None
        if action.target_component_ref:
            component_node = await _upsert_node(
                db, model_id=model.id, node_type="component", external_ref=action.target_component_ref,
                display_name=action.target_component_ref,
                parent_node_id=screen_node.id if screen_node else None, existing=nodes_by_key,
            )
            if screen_node is not None:
                await add_edge("CONTAINS", screen_node, component_node)
        elif action.action_family in ("click", "input", "select") and action.target_element_ref:
            gaps.append({
                "gap_type": "MISSING_COMPONENT", "severity": "warning",
                "evidence": {"action_id": action.id, "sequence": action.sequence},
                "remediation": "Correct this action's component reference in Live Discovery Session and rebuild.",
            })

        if action.target_element_ref:
            parent_node = component_node or screen_node
            element_node = await _upsert_node(
                db, model_id=model.id, node_type="element", external_ref=action.target_element_ref,
                display_name=action.target_semantic or action.target_element_ref,
                parent_node_id=parent_node.id if parent_node else None, existing=nodes_by_key,
            )
            if parent_node is not None:
                key = f"{action.target_element_ref}"
                if key in element_parent_seen and element_parent_seen[key] != parent_node.id:
                    gaps.append({
                        "gap_type": "AMBIGUOUS_ELEMENT", "severity": "warning", "node_id": element_node.id,
                        "evidence": {"action_id": action.id, "element_ref": action.target_element_ref},
                        "remediation": "This element was captured under two different parents — confirm the correct one.",
                    })
                element_parent_seen[key] = parent_node.id
                await add_edge("CONTAINS", parent_node, element_node)

            if action.locator_evidence or action.locator_confidence is not None:
                confidence = action.locator_confidence
                db.add(
                    ApplicationModelLocatorEvidence(
                        node_id=element_node.id,
                        locator_value=(action.locator_evidence or {}).get("value") if action.locator_evidence else None,
                        locator_type=(action.locator_evidence or {}).get("type") if action.locator_evidence else None,
                        confidence=confidence, status="candidate", source_action_id=action.id,
                    )
                )
                if confidence is not None and confidence < LOW_CONFIDENCE_THRESHOLD:
                    gaps.append({
                        "gap_type": "UNSTABLE_LOCATOR", "severity": "warning", "node_id": element_node.id,
                        "evidence": {"confidence": confidence, "action_id": action.id},
                        "remediation": "Confirm a fallback locator for this element before publishing.",
                    })
            else:
                gaps.append({
                    "gap_type": "UNSTABLE_LOCATOR", "severity": "warning", "node_id": element_node.id,
                    "evidence": {"action_id": action.id, "reason": "no locator evidence captured"},
                    "remediation": "Re-record this action or add a fallback locator before publishing.",
                })
        elif action.action_family in ("click", "input", "select"):
            gaps.append({
                "gap_type": "MISSING_ELEMENT", "severity": "critical",
                "evidence": {"action_id": action.id, "sequence": action.sequence},
                "remediation": "Correct this action's element reference in Live Discovery Session and rebuild.",
            })

        if screen_node is not None:
            if (
                action.action_family == "navigate"
                and previous_screen_node is not None
                and previous_screen_node.id != screen_node.id
            ):
                await add_edge("NAVIGATES_TO", previous_screen_node, screen_node)
            previous_screen_node = screen_node

    # A model that discovered nothing is not a clean model — it is no model.
    #
    # Every check downstream is phrased as the *absence* of a gap ("no missing
    # screens", "no unresolved critical blocker"), so a walk that produced zero
    # nodes satisfied all of them vacuously: 0 screens, 0 elements, 0 gaps, and
    # an approvable draft grounding nothing. Observed in practice — a completed
    # session whose actions carried no screen/component/element references built
    # a model that passed every governance row while being empty.
    #
    # Raised as a gap rather than a special case so it flows through the
    # controls that already exist: approve() and publish() refuse on any open
    # critical gap, and the readiness rows key off MISSING_SCREEN.
    if not any(node.node_type == "screen" for node in nodes_by_key.values()):
        gaps.append({
            "gap_type": "MISSING_SCREEN",
            "severity": "critical",
            "evidence": {
                "session_id": session_id,
                "actions_walked": len(actions),
                "reason": "no action in the source session identified a screen",
            },
            "remediation": (
                "This session recorded no screen references, so there is nothing to ground "
                "tests against. Re-record it so each action names the screen it acted on, "
                "then rebuild."
            ),
        })

    for gap in gaps:
        db.add(ApplicationModelGap(model_id=model.id, status="open", **gap))

    await _log_activity(db, model=model, event_type=event_type, actor_id=actor_id)
    await db.commit()
    await db.refresh(model)
    return model


async def compute_kpis(db: AsyncSession, model: ApplicationModel) -> dict[str, Any]:
    nodes_result = await db.execute(select(ApplicationModelNode).where(ApplicationModelNode.model_id == model.id))
    nodes = list(nodes_result.scalars().all())
    gaps_result = await db.execute(select(ApplicationModelGap).where(ApplicationModelGap.model_id == model.id))
    gaps = list(gaps_result.scalars().all())
    open_gaps = [g for g in gaps if g.status == "open"]
    critical_open = [g for g in open_gaps if g.severity == "critical"]
    return {
        "screens": len([n for n in nodes if n.node_type == "screen"]),
        "components": len([n for n in nodes if n.node_type == "component"]),
        "elements": len([n for n in nodes if n.node_type == "element"]),
        "journeys": 0,
        "apis": 0,
        "gaps_open": len(open_gaps),
        "gaps_critical_open": len(critical_open),
        "gaps_total": len(gaps),
    }


async def is_stale(db: AsyncSession, model: ApplicationModel) -> bool:
    if model.source_session_id is None:
        return False
    result = await db.execute(
        select(DiscoveryAction).where(DiscoveryAction.session_id == model.source_session_id)
    )
    current_action_count = len(list(result.scalars().all()))
    return current_action_count > model.built_from_action_count


async def submit_for_review(db: AsyncSession, model: ApplicationModel, *, actor_id: int) -> ApplicationModel:
    _require_mutable(model)
    if model.status not in ("draft", "changes_requested"):
        raise ApplicationModelError(409, "INVALID_TRANSITION", f"Cannot submit for review from '{model.status}'.")
    model.status = "pending_review"
    await _log_activity(db, model=model, event_type="submitted_for_review", actor_id=actor_id)
    await db.commit()
    await db.refresh(model)
    return model


async def request_changes(db: AsyncSession, model: ApplicationModel, *, actor_id: int, reason: str) -> ApplicationModel:
    if model.status != "pending_review":
        raise ApplicationModelError(409, "INVALID_TRANSITION", "Only a model pending review can have changes requested.")
    if not reason or not reason.strip():
        raise ApplicationModelError(422, "REASON_REQUIRED", "Requesting changes requires a reason.")
    model.status = "changes_requested"
    model.reviewed_by = actor_id
    model.reviewed_at = datetime.now(timezone.utc)
    model.decision_reason = reason
    await _log_activity(db, model=model, event_type="changes_requested", actor_id=actor_id, reason=reason)
    await db.commit()
    await db.refresh(model)
    return model


async def reject(db: AsyncSession, model: ApplicationModel, *, actor_id: int, reason: str) -> ApplicationModel:
    if model.status != "pending_review":
        raise ApplicationModelError(409, "INVALID_TRANSITION", "Only a model pending review can be rejected.")
    if not reason or not reason.strip():
        raise ApplicationModelError(422, "REASON_REQUIRED", "Rejecting a model requires a reason.")
    model.status = "rejected"
    model.reviewed_by = actor_id
    model.reviewed_at = datetime.now(timezone.utc)
    model.decision_reason = reason
    await _log_activity(db, model=model, event_type="rejected", actor_id=actor_id, reason=reason)
    await db.commit()
    await db.refresh(model)
    return model


async def approve(db: AsyncSession, model: ApplicationModel, *, actor_id: int, reason: str | None) -> ApplicationModel:
    if model.status != "pending_review":
        raise ApplicationModelError(409, "INVALID_TRANSITION", "Only a model pending review can be approved.")
    if model.built_by == actor_id and get_settings().require_separate_approver:
        raise ApplicationModelError(
            409, "SEPARATION_OF_DUTY_VIOLATION",
            "The user who built this model cannot also approve it. Set "
            "REQUIRE_SEPARATE_APPROVER=false for a single-operator deployment.",
        )
    gaps_result = await db.execute(
        select(ApplicationModelGap).where(
            ApplicationModelGap.model_id == model.id, ApplicationModelGap.severity == "critical",
            ApplicationModelGap.status == "open",
        )
    )
    if gaps_result.scalars().first() is not None:
        raise ApplicationModelError(409, "CRITICAL_GAP_OPEN", "Unresolved critical gaps must be resolved before approval.")
    model.status = "approved"
    model.approved_by = actor_id
    model.approved_at = datetime.now(timezone.utc)
    if reason:
        model.decision_reason = reason
    await _log_activity(db, model=model, event_type="approved", actor_id=actor_id, reason=reason)
    await db.commit()
    await db.refresh(model)
    return model


async def publish(db: AsyncSession, model: ApplicationModel, *, actor_id: int) -> ApplicationModel:
    if model.status != "approved":
        raise ApplicationModelError(409, "INVALID_TRANSITION", "Only an approved model can be published.")
    gaps_result = await db.execute(
        select(ApplicationModelGap).where(
            ApplicationModelGap.model_id == model.id, ApplicationModelGap.severity == "critical",
            ApplicationModelGap.status == "open",
        )
    )
    if gaps_result.scalars().first() is not None:
        raise ApplicationModelError(409, "CRITICAL_GAP_OPEN", "Unresolved critical gaps must be resolved before publication.")

    prior_result = await db.execute(
        select(ApplicationModel).where(
            ApplicationModel.project_id == model.project_id, ApplicationModel.application_id == model.application_id,
            ApplicationModel.status == "published",
        )
    )
    for prior in prior_result.scalars().all():
        prior.status = "superseded"

    model.status = "published"
    model.published_by = actor_id
    model.published_at = datetime.now(timezone.utc)
    await _log_activity(db, model=model, event_type="published", actor_id=actor_id)
    await db.commit()
    await db.refresh(model)
    return model


async def create_new_draft(db: AsyncSession, model: ApplicationModel, *, actor_id: int) -> ApplicationModel:
    if model.status not in ("approved", "published", "rejected"):
        raise ApplicationModelError(
            409, "INVALID_TRANSITION", "A new draft can only be created from an approved, published or rejected model."
        )
    new_model = ApplicationModel(
        project_id=model.project_id, application_id=model.application_id, source_session_id=model.source_session_id,
        version=model.version + 1, parent_model_id=model.id, is_current=True, status="draft",
        built_by=actor_id, built_at=datetime.now(timezone.utc),
    )
    model.is_current = False
    db.add(new_model)
    await db.flush()
    await _log_activity(db, model=new_model, event_type="new_draft_created", actor_id=actor_id)
    await db.commit()
    await db.refresh(new_model)
    return new_model


async def rename_node(db: AsyncSession, model: ApplicationModel, node_id: int, *, display_name: str, actor_id: int) -> ApplicationModelNode:
    _require_mutable(model)
    node = await db.get(ApplicationModelNode, node_id)
    if node is None or node.model_id != model.id:
        raise ApplicationModelError(404, "NODE_NOT_FOUND", "Node not found in this model.")
    old_name = node.display_name
    node.display_name = display_name
    await _log_activity(
        db, model=model, event_type="node_renamed", actor_id=actor_id, node_id=node.id,
        old_value={"display_name": old_name}, new_value={"display_name": display_name},
    )
    await db.commit()
    await db.refresh(node)
    return node


async def _locator_action(
    db: AsyncSession, model: ApplicationModel, node_id: int, *, status: str, actor_id: int,
    locator_value: str | None = None, locator_type: str | None = None, reason: str | None = None,
) -> ApplicationModelLocatorEvidence:
    _require_mutable(model)
    node = await db.get(ApplicationModelNode, node_id)
    if node is None or node.model_id != model.id:
        raise ApplicationModelError(404, "NODE_NOT_FOUND", "Node not found in this model.")
    entry = ApplicationModelLocatorEvidence(
        node_id=node.id, locator_value=locator_value, locator_type=locator_type, status=status,
        reason=reason, created_by=actor_id,
    )
    db.add(entry)
    if status == "unstable":
        gap_result = await db.execute(
            select(ApplicationModelGap).where(
                ApplicationModelGap.model_id == model.id, ApplicationModelGap.node_id == node.id,
                ApplicationModelGap.gap_type == "UNSTABLE_LOCATOR", ApplicationModelGap.status == "open",
            )
        )
        if gap_result.scalars().first() is None:
            db.add(
                ApplicationModelGap(
                    model_id=model.id, gap_type="UNSTABLE_LOCATOR", severity="warning", node_id=node.id,
                    evidence={}, remediation="Add a fallback locator or re-confirm from live evidence.", status="open",
                )
            )
    elif status == "confirmed":
        gap_result = await db.execute(
            select(ApplicationModelGap).where(
                ApplicationModelGap.model_id == model.id, ApplicationModelGap.node_id == node.id,
                ApplicationModelGap.gap_type == "UNSTABLE_LOCATOR", ApplicationModelGap.status == "open",
            )
        )
        for gap in gap_result.scalars().all():
            gap.status = "resolved"
            gap.resolved_by = actor_id
            gap.resolved_at = datetime.now(timezone.utc)
    await _log_activity(
        db, model=model, event_type=f"locator_{status}", actor_id=actor_id, node_id=node.id, reason=reason,
    )
    await db.commit()
    await db.refresh(entry)
    return entry


async def confirm_locator(db: AsyncSession, model: ApplicationModel, node_id: int, *, actor_id: int) -> ApplicationModelLocatorEvidence:
    return await _locator_action(db, model, node_id, status="confirmed", actor_id=actor_id)


async def mark_locator_unstable(
    db: AsyncSession, model: ApplicationModel, node_id: int, *, actor_id: int, reason: str,
) -> ApplicationModelLocatorEvidence:
    return await _locator_action(db, model, node_id, status="unstable", actor_id=actor_id, reason=reason)


async def add_fallback_locator(
    db: AsyncSession, model: ApplicationModel, node_id: int, *, actor_id: int, locator_value: str, locator_type: str | None,
) -> ApplicationModelLocatorEvidence:
    return await _locator_action(
        db, model, node_id, status="fallback", actor_id=actor_id, locator_value=locator_value, locator_type=locator_type,
    )


async def resolve_gap(db: AsyncSession, model: ApplicationModel, gap_id: int, *, actor_id: int, reviewer_notes: str | None) -> ApplicationModelGap:
    _require_mutable(model)
    gap = await db.get(ApplicationModelGap, gap_id)
    if gap is None or gap.model_id != model.id:
        raise ApplicationModelError(404, "GAP_NOT_FOUND", "Gap not found in this model.")
    gap.status = "resolved"
    gap.resolved_by = actor_id
    gap.resolved_at = datetime.now(timezone.utc)
    if reviewer_notes:
        gap.reviewer_notes = reviewer_notes
    await _log_activity(db, model=model, event_type="gap_resolved", actor_id=actor_id, node_id=gap.node_id, reason=reviewer_notes)
    await db.commit()
    await db.refresh(gap)
    return gap
