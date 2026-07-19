"""Grounded Automation PoC models — evidence-first script generation.

Deliberately isolated from the existing Automation Studios: PoC-prefixed
tables, no columns added to any existing table, and only *references*
(FKs) into test_cases / projects / automation_scripts. Dropping the two
tables (migration 038 downgrade) removes the PoC without a trace.

Design terms (review-corrected):
  - "Application State Evidence Package" (PocStateEvidence) — one captured,
    verified application state: URL alone does NOT identify a state, so each
    package carries a state_fingerprint (hash over url + title + element
    catalog) plus persona/environment context and prev-state linkage.
  - The coverage gate result (four dimensions per step: action / data /
    assertion / cleanup evidence) is stored as JSON on the run row — it is
    a verdict document, not a queryable entity, so it does not get its own
    table in the PoC.
"""
from sqlalchemy import CheckConstraint, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

# Stage machine. Strictly forward except failed/cancelled (terminal from any
# active state) and gate_blocked → capturing (user resumes capture after
# fixing gaps):
#   draft → routing_ready → capturing → (awaiting_confirmation ⇄ capturing)
#         → gate_passed | gate_blocked → generating → generated
POC_RUN_STATUSES = (
    "draft",
    "routing_ready",
    "capturing",
    "awaiting_confirmation",
    "gate_passed",
    "gate_blocked",
    "generating",
    "generated",
    "failed",
    "cancelled",
)

POC_CAPTURE_MODES = ("automated", "assisted", "manual_guided")


class PocGroundingRun(TimestampMixin, Base):
    """One per-test-case grounded-generation pipeline run.

    Umbrella row tying together: the routing decision (TC-level and
    step-level), the capture AgentRun(s), the persisted evidence packages,
    the coverage-gate verdict, and — after the gate passes — the generation
    AgentRun whose output lands in the standard automation_scripts pipeline
    (contract → compile → static gate → dry run → repair, unchanged).
    """

    __tablename__ = "poc_grounding_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(POC_RUN_STATUSES) + "')",
            name="ck_poc_grounding_runs_status",
        ),
        CheckConstraint(
            "capture_mode IN ('" + "','".join(POC_CAPTURE_MODES) + "')",
            name="ck_poc_grounding_runs_capture_mode",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Read-only reference — the PoC never mutates the TestCase row itself.
    test_case_id: Mapped[int] = mapped_column(
        ForeignKey("test_cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    application_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_applications.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")
    capture_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="automated")

    # Snapshot of resolved inputs: environment, target_url, application_name,
    # test_case display id/title, max_steps, max_minutes.
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Routing decision (rules-first classifier): overall classification +
    # per-step adapter + per-assertion validation channel + confidence.
    routing: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Four-dimension coverage-gate verdict (action/data/assertion/cleanup
    # evidence per step, unsupported references, generation_allowed).
    coverage: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Assisted mode: the step the capture agent paused on + the candidate
    # elements it proposes; the confirm-step endpoint folds the user's
    # choice into config["confirmed_actions"] and resumes capture.
    pending_confirmation: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # {"capture": [<agent_run_id>, ...], "generation": <agent_run_id>}
    agent_runs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # AutomationScript rows produced by the (gated) generation step. The
    # scripts themselves live in the standard automation inventory so the
    # existing review/approval lifecycle applies to them untouched.
    script_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project")
    test_case: Mapped["TestCase"] = relationship("TestCase")
    evidence: Mapped[list["PocStateEvidence"]] = relationship(
        "PocStateEvidence", back_populates="grounding_run", cascade="all, delete-orphan"
    )


class PocStateEvidence(TimestampMixin, Base):
    """One Application State Evidence Package captured during a walk.

    Everything the coverage gate and generation are allowed to reference
    must exist here first — that is the "no guesswork" contract. Snapshot
    text is PII-masked (mask_snapshot_text) BEFORE persistence, same policy
    as AgentLog/locator_map.
    """

    __tablename__ = "poc_state_evidence"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grounding_run_id: Mapped[int] = mapped_column(
        ForeignKey("poc_grounding_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Order within the walk; 0 = entry state.
    sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # sha256 over (url, title, sorted element names) — application state
    # identity, NOT just screen/URL identity (same URL can be many states).
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    environment: Mapped[str | None] = mapped_column(String(80), nullable=True)
    viewport: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Ranked interactive-element catalog (same shape locator_map/discovery
    # produce: element_name, role, accessible_name, recommended_locator,
    # recommended_strategy, confidence_score, href).
    elements: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    # Masked accessibility-tree excerpt — assertion grounding searches this.
    snapshot_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    screenshot_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    # Live blocker signals seen on this state (OTP/CAPTCHA/manual-only).
    blockers: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # Console errors captured on this state (best effort).
    console_evidence: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    # The TC step index whose action produced this state (None for entry).
    produced_by_step: Mapped[int | None] = mapped_column(Integer, nullable=True)
    prev_evidence_id: Mapped[int | None] = mapped_column(
        ForeignKey("poc_state_evidence.id", ondelete="SET NULL"), nullable=True
    )

    grounding_run: Mapped["PocGroundingRun"] = relationship(
        "PocGroundingRun", back_populates="evidence"
    )
