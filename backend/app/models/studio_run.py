from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import TimestampMixin

# Stage machine for a Playwright AI Studio run. Statuses advance strictly
# forward except failed/cancelled (terminal from any active state):
#   draft → exploring → plan_ready → generating → scripts_ready
#         → executing → healing → completed
# "healing" is reserved for a future automatic post-execution repair sweep;
# today executing runs move straight to completed once every linked
# ExecutionRun is terminal (see studio_service._reconcile_status).
STUDIO_RUN_STATUSES = (
    "draft",
    "exploring",
    "plan_ready",
    "generating",
    "scripts_ready",
    "executing",
    "healing",
    "completed",
    "failed",
    "cancelled",
)


class StudioRun(TimestampMixin, Base):
    """One end-to-end Playwright AI Studio pipeline run (application-first).

    Unlike the /automation flow (which starts from approved test cases),
    a Studio run starts from an application URL: the planner agent explores
    the live app and proposes test cases itself, and every downstream stage
    is approved in bulk rather than per artifact. The run row is the
    umbrella that ties together the planner AgentRun, the generation-wave
    AgentRuns, the materialized TestCase rows, and the batch ExecutionRuns —
    each of those stays a first-class row in its own table so existing
    traceability/coverage/audit machinery keeps working unchanged.
    """

    __tablename__ = "studio_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('" + "','".join(STUDIO_RUN_STATUSES) + "')",
            name="ck_studio_runs_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft")

    # Planner Input form snapshot: application_id, environment, target_url,
    # objective, coverage_types, excluded_paths, browser, max_pages,
    # max_minutes, framework, runner_mode, parallelism, timeout_seconds.
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Planner agent output: explored pages + proposed test cases (data, not
    # code — ADR-001). Approval marks/edits from the Test Plan Review step
    # are folded in here before materialization.
    plan: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Materialized TestCase row ids (set by approve_plan).
    test_case_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # {"planner": <agent_run_id>, "generation": [<agent_run_id>, ...]}
    agent_runs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Batch ExecutionRun ids created by approve_scripts / execution chunking.
    execution_run_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    project: Mapped["Project"] = relationship("Project")
