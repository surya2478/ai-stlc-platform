"""Per-test-case grounding matrix.

Ported from the retired engine's `build_grounding_matrix`, rescoped from a
workspace row to an explicit `(test_case, model)` pair so a suite can build it
for any member. The traversal is unchanged: test case steps -> DiscoveryAction
by `test_step_ref` -> ApplicationModelNode by `(node_type, external_ref)` ->
NetworkEvent and ApplicationModelGap.

`external_validation` is reported as NOT_EVALUATED because no external
validation subsystem exists yet — it is not a placeholder for a value we
could compute.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_model import ApplicationModel, ApplicationModelGap, ApplicationModelNode
from app.models.discovery_session import DiscoveryAction
from app.models.network_event import NetworkEvent
from app.models.test_case import TestCase

_LOCATOR_CRITICAL_GAPS = {"MISSING_SCREEN", "MISSING_COMPONENT", "MISSING_ELEMENT"}
_LOCATOR_WARNING_GAPS = {"AMBIGUOUS_ELEMENT", "UNSTABLE_LOCATOR"}


def _ungrounded_rows(steps: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "step_number": s.get("step_number") if isinstance(s, dict) else i + 1,
            "action": s.get("action") if isinstance(s, dict) else str(s),
            "screen": None,
            "element": None,
            "locator_status": None,
            "apis": [],
            "external_validation": "NOT_EVALUATED",
            "evidence_count": 0,
            "status": "Missing",
        }
        for i, s in enumerate(steps)
    ]


async def build_grounding_matrix(
    db: AsyncSession, *, test_case: TestCase | None, model: ApplicationModel | None
) -> list[dict[str, Any]]:
    steps = list(test_case.steps or []) if test_case else []
    if not steps or model is None:
        return _ungrounded_rows(steps)

    if model.source_session_id is None:
        return _ungrounded_rows(steps)

    actions_result = await db.execute(
        select(DiscoveryAction).where(DiscoveryAction.session_id == model.source_session_id)
    )
    actions = list(actions_result.scalars().all())
    actions_by_step: dict[str, list[DiscoveryAction]] = {}
    for a in actions:
        if a.test_step_ref:
            actions_by_step.setdefault(a.test_step_ref, []).append(a)

    nodes_result = await db.execute(select(ApplicationModelNode).where(ApplicationModelNode.model_id == model.id))
    nodes_by_ref = {(n.node_type, n.external_ref): n for n in nodes_result.scalars().all()}

    gaps_result = await db.execute(
        select(ApplicationModelGap).where(
            ApplicationModelGap.model_id == model.id, ApplicationModelGap.status == "open"
        )
    )
    gaps = list(gaps_result.scalars().all())
    action_ids_with_critical_gap = {
        g.evidence.get("action_id") for g in gaps if g.gap_type in _LOCATOR_CRITICAL_GAPS and g.evidence.get("action_id")
    }
    action_ids_with_warning_gap = {
        g.evidence.get("action_id") for g in gaps if g.gap_type in _LOCATOR_WARNING_GAPS and g.evidence.get("action_id")
    }

    action_ids = [a.id for a in actions]
    network_events_by_action: dict[int, list[NetworkEvent]] = {}
    if action_ids:
        events_result = await db.execute(select(NetworkEvent).where(NetworkEvent.action_id.in_(action_ids)))
        for ev in events_result.scalars().all():
            if ev.action_id:
                network_events_by_action.setdefault(ev.action_id, []).append(ev)

    rows: list[dict[str, Any]] = []
    for step in steps:
        step_number = step.get("step_number") if isinstance(step, dict) else None
        action_text = step.get("action") if isinstance(step, dict) else str(step)
        matching = actions_by_step.get(str(step_number), []) if step_number is not None else []

        screen_ref = next((a.target_screen_ref for a in matching if a.target_screen_ref), None)
        element_ref = next((a.target_element_ref for a in matching if a.target_element_ref), None)
        screen_node = nodes_by_ref.get(("screen", screen_ref)) if screen_ref else None
        element_node = nodes_by_ref.get(("element", element_ref)) if element_ref else None

        apis: list[str] = []
        evidence_count = 0
        has_critical_gap = False
        has_warning_gap = False
        for a in matching:
            evidence_count += len(a.evidence_refs or [])
            if a.id in action_ids_with_critical_gap:
                has_critical_gap = True
            if a.id in action_ids_with_warning_gap:
                has_warning_gap = True
            for ev in network_events_by_action.get(a.id, []):
                if ev.method and ev.path:
                    apis.append(f"{ev.method} {ev.path}")

        if not matching:
            status = "Missing"
        elif has_critical_gap:
            status = "Blocked"
        elif has_warning_gap:
            status = "Ambiguous"
        elif screen_ref and (not element_ref or element_node is not None):
            status = "Complete"
        else:
            status = "Partial"

        rows.append(
            {
                "step_number": step_number,
                "action": action_text,
                "screen": screen_node.display_name if screen_node else screen_ref,
                "element": element_node.display_name if element_node else element_ref,
                "locator_status": (element_node.state if element_node else None),
                "apis": sorted(set(apis)),
                "external_validation": "NOT_EVALUATED",
                "evidence_count": evidence_count,
                "status": status,
            }
        )
    return rows
