"""Loads everything one Live Recorder session needs, in bulk.

This module is the only place in the package that queries the database for
read purposes. Step derivation, gap detection, the recording summary and IR
emission are all pure functions over the `RecordingContext` returned here —
the same split `app.services.automation_suite.inheritance` uses, and for the
same reason: a per-action query loop would issue hundreds of statements for a
session with a hundred recorded actions, while this issues a fixed number
regardless of how long the recording ran.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.application_model import ApplicationModel
from app.models.automation_suite import AutomationSuite, AutomationSuiteTestCase
from app.models.discovery_session import DiscoveryAction, DiscoveryCapture, DiscoverySession, DiscoverySessionEvent
from app.models.project_application import ProjectApplication
from app.models.recording_session import (
    AutomationIrDraft,
    RecordingCheckpoint,
    RecordingDataBinding,
    RecordingNote,
    RecordingSegment,
    RecordingStepMapping,
    RecordingStepState,
)
from app.models.test_case import TestCase


@dataclass(frozen=True)
class RecordingContext:
    """One session and everything hanging off it, loaded once."""

    session: DiscoverySession
    test_case: TestCase | None
    suite: AutomationSuite | None
    member: AutomationSuiteTestCase | None
    application: ProjectApplication | None
    application_model: ApplicationModel | None
    actions: list[DiscoveryAction] = field(default_factory=list)
    mappings: list[RecordingStepMapping] = field(default_factory=list)
    step_states: list[RecordingStepState] = field(default_factory=list)
    checkpoints: list[RecordingCheckpoint] = field(default_factory=list)
    segments: list[RecordingSegment] = field(default_factory=list)
    bindings: list[RecordingDataBinding] = field(default_factory=list)
    notes: list[RecordingNote] = field(default_factory=list)
    captures: list[DiscoveryCapture] = field(default_factory=list)
    events: list[DiscoverySessionEvent] = field(default_factory=list)
    ir_draft: AutomationIrDraft | None = None

    # ── Derived lookups every consumer needs, built once here rather than
    # rebuilt in each pure function. ──

    @property
    def actions_by_id(self) -> dict[int, DiscoveryAction]:
        return {a.id: a for a in self.actions}

    @property
    def mapping_by_action_id(self) -> dict[int, RecordingStepMapping]:
        return {m.action_id: m for m in self.mappings}

    @property
    def mappings_by_step_key(self) -> dict[str, list[RecordingStepMapping]]:
        grouped: dict[str, list[RecordingStepMapping]] = {}
        for mapping in self.mappings:
            grouped.setdefault(mapping.step_key, []).append(mapping)
        return grouped

    @property
    def step_state_by_key(self) -> dict[str, RecordingStepState]:
        return {s.step_key: s for s in self.step_states}

    @property
    def checkpoints_by_step_key(self) -> dict[str, list[RecordingCheckpoint]]:
        grouped: dict[str, list[RecordingCheckpoint]] = {}
        for checkpoint in self.checkpoints:
            if checkpoint.step_key:
                grouped.setdefault(checkpoint.step_key, []).append(checkpoint)
        return grouped

    @property
    def captures_by_action_id(self) -> dict[int, list[DiscoveryCapture]]:
        grouped: dict[int, list[DiscoveryCapture]] = {}
        for capture in self.captures:
            if capture.action_id is not None:
                grouped.setdefault(capture.action_id, []).append(capture)
        return grouped

    @property
    def source_steps(self) -> list[dict]:
        """The live test case's steps. Never a stored copy — Section 4."""
        if self.test_case is None:
            return []
        steps = self.test_case.steps or []
        return [s for s in steps if isinstance(s, dict)]


async def load(db: AsyncSession, session: DiscoverySession) -> RecordingContext:
    test_case = await db.get(TestCase, session.test_case_id) if session.test_case_id else None
    suite = await db.get(AutomationSuite, session.suite_id) if session.suite_id else None
    member = (
        await db.get(AutomationSuiteTestCase, session.suite_member_id) if session.suite_member_id else None
    )
    application = await db.get(ProjectApplication, session.application_id)

    application_model = None
    if application is not None:
        result = await db.execute(
            select(ApplicationModel)
            .where(
                ApplicationModel.application_id == application.id,
                ApplicationModel.is_current.is_(True),
            )
            .limit(1)
        )
        application_model = result.scalar_one_or_none()

    async def _all(model, order_by=None):
        query = select(model).where(model.session_id == session.id)
        if order_by is not None:
            query = query.order_by(order_by)
        result = await db.execute(query)
        return list(result.scalars().all())

    ir_result = await db.execute(
        select(AutomationIrDraft)
        .where(AutomationIrDraft.session_id == session.id, AutomationIrDraft.is_current.is_(True))
        .limit(1)
    )

    return RecordingContext(
        session=session,
        test_case=test_case,
        suite=suite,
        member=member,
        application=application,
        application_model=application_model,
        actions=await _all(DiscoveryAction, DiscoveryAction.sequence),
        mappings=await _all(RecordingStepMapping, RecordingStepMapping.id),
        step_states=await _all(RecordingStepState, RecordingStepState.id),
        checkpoints=await _all(RecordingCheckpoint, RecordingCheckpoint.id),
        segments=await _all(RecordingSegment, RecordingSegment.sequence),
        bindings=await _all(RecordingDataBinding, RecordingDataBinding.id),
        notes=await _all(RecordingNote, RecordingNote.id),
        captures=await _all(DiscoveryCapture, DiscoveryCapture.id),
        events=await _all(DiscoverySessionEvent, DiscoverySessionEvent.occurred_at),
        ir_draft=ir_result.scalar_one_or_none(),
    )
