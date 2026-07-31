"""052 - P1-S7 UI-046 Suite Execution Command Center

Additive only. Builds the suite-to-execution path that UI-018 Phase B
deliberately left out: `execution_runs` gains a link to the immutable published
snapshot it is executing, plus the run-level lifecycle, control and outcome
state the command center needs. See the UI-046 contract Section 2.1.12 for the
scoped-slice boundary this migration serves.

Four decisions worth stating, because each one is expensive to reverse:

1. `lifecycle_state` is a NEW column rather than a widening of `status`.
   `execution_runs.status` already carries a check constraint and its own
   vocabulary that the Execution Dashboard aggregates on (migration 024).
   Overloading it would change the meaning of every historical manual and AI
   run. Suite runs write both: `status` stays truthful for the existing
   dashboard, `lifecycle_state` carries the command-center state machine.
   All new columns are nullable or defaulted so every pre-existing run row
   remains valid with no data migration.

2. All eight outcome states land now, including the two that only the deferred
   evidence types can produce. Retrofitting a check constraint over live
   execution rows is materially harder than getting the vocabulary right once.

3. `execution_run_events.sequence` is a monotonic per-run counter with a unique
   constraint, not a timestamp. The command center polls `?after={sequence}`
   because this platform has no SSE or WebSocket transport — the same
   DB-as-source-of-truth pattern `discovery_sessions.pending_command` uses, and
   for the same reason. Timestamps collide under parallel runners; a sequence
   cannot, so reconnection can neither lose nor duplicate an event.

4. `execution_runs.run_version` exists so a control command can carry
   `expectedRunVersion` and be rejected rather than silently applied to a run
   whose state moved underneath the operator (contract Section 11).

Nothing here writes `source_type`. Note for callers: migration 007 added that
column as NOT NULL with a server default while the ORM model still declares it
nullable, so a caller that passes `source_type=None` explicitly fails at insert
while one that omits it succeeds. Run-creation code must set it explicitly.

Revision ID: 052
Revises: 051
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "052"
down_revision = "051"
branch_labels = None
depends_on = None


# Contract Section 3.1 run states, plus the request/terminal states the control
# semantics in Section 9 need. PAUSE_REQUESTED and STOP_REQUESTED are distinct
# from PAUSED and STOPPED because the UI must not claim a control took effect
# before the backend acknowledges it.
RUN_LIFECYCLE_STATES = (
    "READINESS_PENDING",
    "BLOCKED_BEFORE_START",
    "QUEUED",
    "RUNNING",
    "PAUSE_REQUESTED",
    "PAUSED",
    "STOP_REQUESTED",
    "STOPPED",
    "CANCELLED",
    "COMPLETED",
)

# The eight deterministic outcomes required by the tracker's P1-S7 checklist.
# A run-level or item-level classification. Never inferred from the runner's
# exit code alone — see services/execution_command_center/outcomes.py.
OUTCOMES = (
    "PASS",
    "FAIL",
    "INCONCLUSIVE",
    "BLOCKED",
    "ENVIRONMENT_FAILURE",
    "DATA_FAILURE",
    "AUTOMATION_FAILURE",
    "POLICY_BLOCKED",
)

# An item that has not been classified yet is PENDING; SKIPPED is a real
# terminal result (Section 4.1 shows it only when non-zero) but is not an
# outcome, because nothing was evaluated.
ITEM_RESULTS = ("PENDING", "SKIPPED") + OUTCOMES

ITEM_LIFECYCLE_STATES = (
    "QUEUED",
    "STARTING",
    "RUNNING",
    "PAUSED",
    "COMPLETED",
)

STEP_STATUSES = ("pending", "running", "passed", "failed", "skipped")

CONTROL_ACTIONS = (
    "PAUSE_AFTER_CURRENT",
    "RESUME",
    "STOP_GRACEFULLY",
    "CANCEL_NOW",
    "EMERGENCY_STOP",
)

COMMAND_STATES = ("REQUESTED", "ACKNOWLEDGED", "APPLIED", "REJECTED", "SUPERSEDED")

# Section 7.4 evidence list. `dom`, `accessibility`, `event` and `video` are in
# the vocabulary but deferred in this slice: the schema accepts them so a later
# capture path needs no migration, and the UI states why they are unavailable
# rather than implying they were captured.
EVIDENCE_TYPES = (
    "screenshot",
    "video",
    "trace",
    "log",
    "api",
    "network",
    "console",
    "database",
    "dom",
    "accessibility",
    "event",
)

# `unavailable` is a first-class state, not an absence. Section 14.12 requires
# missing mandatory evidence to stay visible and be able to drive INCONCLUSIVE,
# which a missing row could not express.
EVIDENCE_STATUSES = ("pending", "captured", "unavailable")

# Section 7.3 assertion sources.
ASSERTION_SOURCES = ("ui", "api", "db", "oms", "billing", "provisioning", "network")


def _in_list(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ('" + "','".join(values) + "')"


def upgrade() -> None:
    # ── The suite-to-execution link and run-level command state ──────────────
    op.add_column(
        "execution_runs",
        sa.Column(
            "suite_id",
            sa.Integer(),
            sa.ForeignKey("automation_suites.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # The snapshot, not the suite, is what actually executed. A suite can open a
    # new version after this run finished; the run must keep pointing at the
    # frozen scope it was dispatched from.
    op.add_column(
        "execution_runs",
        sa.Column(
            "suite_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("automation_suite_snapshots.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_execution_runs_suite_id", "execution_runs", ["suite_id"])
    op.create_index(
        "ix_execution_runs_suite_snapshot_id", "execution_runs", ["suite_snapshot_id"]
    )

    # NULL on every pre-existing run: manual, AI and single-script automation
    # runs have no command-center lifecycle and must not acquire a fake one.
    op.add_column(
        "execution_runs", sa.Column("lifecycle_state", sa.String(length=30), nullable=True)
    )
    op.add_column("execution_runs", sa.Column("outcome", sa.String(length=30), nullable=True))
    op.add_column(
        "execution_runs",
        sa.Column("run_version", sa.Integer(), nullable=False, server_default="0"),
    )
    # The single field the orchestrator polls each dispatch boundary. Same
    # pattern as discovery_sessions.pending_command.
    op.add_column(
        "execution_runs", sa.Column("pending_command", sa.String(length=40), nullable=True)
    )
    op.add_column(
        "execution_runs", sa.Column("pending_command_reason", sa.Text(), nullable=True)
    )
    op.add_column(
        "execution_runs",
        sa.Column("pending_command_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    # High-water mark for the event sequence. Held on the run so a new event's
    # number is allocated under the run row's lock rather than a table scan.
    op.add_column(
        "execution_runs",
        sa.Column("event_sequence", sa.Integer(), nullable=False, server_default="0"),
    )
    # Persisted gate result. Kept by value so "why was this run blocked" stays
    # answerable after the environment recovers.
    op.add_column(
        "execution_runs",
        sa.Column("readiness", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "execution_runs",
        sa.Column("readiness_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "execution_runs",
        sa.Column("parallel_limit", sa.Integer(), nullable=False, server_default="1"),
    )
    op.add_column(
        "execution_runs",
        sa.Column("evidence_required_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "execution_runs",
        sa.Column("evidence_captured_total", sa.Integer(), nullable=False, server_default="0"),
    )
    # Trigger provenance (contract Section 3).
    op.add_column(
        "execution_runs", sa.Column("trigger_source", sa.String(length=20), nullable=True)
    )
    op.add_column(
        "execution_runs", sa.Column("execution_purpose", sa.String(length=255), nullable=True)
    )
    op.add_column(
        "execution_runs", sa.Column("correlation_id", sa.String(length=255), nullable=True)
    )
    op.create_index(
        "ix_execution_runs_correlation_id", "execution_runs", ["correlation_id"]
    )

    # Both constrained as "NULL or a known value" so historical rows stay legal.
    op.create_check_constraint(
        "ck_execution_runs_lifecycle_state",
        "execution_runs",
        f"lifecycle_state IS NULL OR {_in_list('lifecycle_state', RUN_LIFECYCLE_STATES)}",
    )
    op.create_check_constraint(
        "ck_execution_runs_outcome",
        "execution_runs",
        f"outcome IS NULL OR {_in_list('outcome', OUTCOMES)}",
    )
    op.create_check_constraint(
        "ck_execution_runs_pending_command",
        "execution_runs",
        f"pending_command IS NULL OR {_in_list('pending_command', CONTROL_ACTIONS)}",
    )

    # ── One row per suite member dispatched in this run ──────────────────────
    op.create_table(
        "execution_run_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_run_id",
            sa.Integer(),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Suite execution sequence. Stable and never rewritten, so Section 6.2's
        # "Reset order" always has an authoritative order to return to.
        sa.Column("order_index", sa.Integer(), nullable=False),
        # SET NULL, not CASCADE: deleting a suite member must not erase the
        # record that it executed.
        sa.Column(
            "suite_test_case_id",
            sa.Integer(),
            sa.ForeignKey("automation_suite_test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "test_case_id",
            sa.Integer(),
            sa.ForeignKey("test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "execution_group_id",
            sa.Integer(),
            sa.ForeignKey("automation_suite_execution_groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "script_id",
            sa.Integer(),
            sa.ForeignKey("automation_scripts.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "application_id",
            sa.Integer(),
            sa.ForeignKey("project_applications.id", ondelete="SET NULL"),
            nullable=True,
        ),
        # Frozen display identity, copied from the snapshot at expansion time.
        # This is the one place copying is correct: the snapshot is already
        # immutable, and the matrix must render what was published even if the
        # live test case is later renamed or deleted.
        sa.Column("test_case_key", sa.String(length=100), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("journey", sa.String(length=200), nullable=True),
        sa.Column("priority", sa.String(length=30), nullable=True),
        sa.Column("framework", sa.String(length=50), nullable=True),
        sa.Column("environment", sa.String(length=100), nullable=True),
        sa.Column("test_case_version", sa.Integer(), nullable=True),
        sa.Column("runner_name", sa.String(length=100), nullable=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column(
            "lifecycle_state",
            sa.String(length=20),
            nullable=False,
            server_default="QUEUED",
        ),
        sa.Column(
            "result", sa.String(length=30), nullable=False, server_default="PENDING"
        ),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("attempts_allowed", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("steps_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("steps_completed", sa.Integer(), nullable=False, server_default="0"),
        # Three counts, because two cannot express the situation honestly:
        # `evidence_required`/`evidence_captured` are the mandatory pair the quorum
        # rule is judged on, and `evidence_total_captured` is every artifact kept.
        # A test whose IR declares no mandatory evidence can still produce a trace
        # and a screenshot, and collapsing that to "0 / 0" would hide real evidence.
        sa.Column("evidence_required", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("evidence_captured", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "evidence_total_captured", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("assertions_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assertions_passed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        # Why this item is not simply passing. Section 6.2 requires the exact
        # reason in the tooltip and inspector, so it is a stored string rather
        # than something the frontend reconstructs from a status.
        sa.Column("attention_reason", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_reason", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # The member entry exactly as it appeared in the published snapshot.
        sa.Column(
            "snapshot_member",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_list("lifecycle_state", ITEM_LIFECYCLE_STATES),
            name="ck_execution_run_items_lifecycle_state",
        ),
        sa.CheckConstraint(
            _in_list("result", ITEM_RESULTS), name="ck_execution_run_items_result"
        ),
        # Section 4.3's reconciliation depends on every item having exactly one
        # slot in the run's order.
        sa.UniqueConstraint(
            "execution_run_id", "order_index", name="uq_execution_run_items_order"
        ),
    )
    op.create_index(
        "ix_execution_run_items_run", "execution_run_items", ["execution_run_id"]
    )
    op.create_index("ix_execution_run_items_project", "execution_run_items", ["project_id"])
    # Drives both the status-card filters and the reconciled summary counts.
    op.create_index(
        "ix_execution_run_items_run_result",
        "execution_run_items",
        ["execution_run_id", "result"],
    )
    op.create_index(
        "ix_execution_run_items_run_lifecycle",
        "execution_run_items",
        ["execution_run_id", "lifecycle_state"],
    )
    # Cursor pagination for Section 14.13's 10,000-item requirement.
    op.create_index(
        "ix_execution_run_items_run_order",
        "execution_run_items",
        ["execution_run_id", "order_index"],
    )

    # ── Per-step progress: the inspector's "6 of 14" ─────────────────────────
    op.create_table(
        "execution_run_item_steps",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_run_item_id",
            sa.Integer(),
            sa.ForeignKey("execution_run_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_number", sa.Integer(), nullable=False),
        sa.Column("action_text", sa.Text(), nullable=True),
        sa.Column("expected_text", sa.Text(), nullable=True),
        sa.Column("actual_text", sa.Text(), nullable=True),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        # Where the step ran, for the inspector's application/page context.
        sa.Column("application_context", sa.String(length=200), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("elapsed_ms", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # A step's status changes as it runs, so it carries TimestampMixin and
        # needs both columns. Same for assertions and evidence below.
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_list("status", STEP_STATUSES), name="ck_execution_run_item_steps_status"
        ),
        sa.UniqueConstraint(
            "execution_run_item_id", "step_number", name="uq_execution_run_item_steps"
        ),
    )
    op.create_index(
        "ix_execution_run_item_steps_item",
        "execution_run_item_steps",
        ["execution_run_item_id"],
    )

    # ── Assertions: what actually decides PASS ──────────────────────────────
    op.create_table(
        "execution_run_assertions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_run_item_id",
            sa.Integer(),
            sa.ForeignKey("execution_run_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "execution_run_item_step_id",
            sa.Integer(),
            sa.ForeignKey("execution_run_item_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.String(length=20), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("expected_value", sa.Text(), nullable=True),
        sa.Column("actual_value", sa.Text(), nullable=True),
        sa.Column(
            "mandatory", sa.Boolean(), nullable=False, server_default=sa.text("true")
        ),
        # NULL means not evaluated yet — Section 7.3 needs a pending count, and
        # a boolean default would silently assert an untested claim.
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_list("source", ASSERTION_SOURCES),
            name="ck_execution_run_assertions_source",
        ),
    )
    op.create_index(
        "ix_execution_run_assertions_item",
        "execution_run_assertions",
        ["execution_run_item_id"],
    )

    # ── Evidence ────────────────────────────────────────────────────────────
    op.create_table(
        "execution_run_evidence",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_run_id",
            sa.Integer(),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # NULL for run-scope evidence such as the orchestrator log.
        sa.Column(
            "execution_run_item_id",
            sa.Integer(),
            sa.ForeignKey("execution_run_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "execution_run_item_step_id",
            sa.Integer(),
            sa.ForeignKey("execution_run_item_steps.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("evidence_type", sa.String(length=30), nullable=False),
        sa.Column(
            "status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column(
            "mandatory", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("file_path", sa.Text(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        # Section 14.14. False means the artifact has not been through the
        # masking pass and must not be served.
        sa.Column(
            "sanitized", sa.Boolean(), nullable=False, server_default=sa.text("false")
        ),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        # Why a mandatory artifact is absent. Required so the UI can explain an
        # INCONCLUSIVE rather than showing a silent gap.
        sa.Column("unavailable_reason", sa.Text(), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_list("evidence_type", EVIDENCE_TYPES),
            name="ck_execution_run_evidence_type",
        ),
        sa.CheckConstraint(
            _in_list("status", EVIDENCE_STATUSES), name="ck_execution_run_evidence_status"
        ),
        # An unavailable artifact must say why; a captured one must have a
        # payload or a file. Enforced here because the quorum rule trusts it.
        sa.CheckConstraint(
            "status <> 'unavailable' OR unavailable_reason IS NOT NULL",
            name="ck_execution_run_evidence_unavailable_reason",
        ),
        sa.CheckConstraint(
            "status <> 'captured' OR file_path IS NOT NULL OR payload IS NOT NULL",
            name="ck_execution_run_evidence_captured_artifact",
        ),
    )
    op.create_index(
        "ix_execution_run_evidence_run", "execution_run_evidence", ["execution_run_id"]
    )
    op.create_index(
        "ix_execution_run_evidence_item",
        "execution_run_evidence",
        ["execution_run_item_id"],
    )

    # ── The event stream the UI polls ───────────────────────────────────────
    op.create_table(
        "execution_run_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_run_id",
            sa.Integer(),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Monotonic per run. See the module docstring for why this is not a
        # timestamp.
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "execution_run_item_id",
            sa.Integer(),
            sa.ForeignKey("execution_run_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(length=60), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint(
            "execution_run_id", "sequence", name="uq_execution_run_events_sequence"
        ),
    )
    # The cursor query: everything after a sequence, in order.
    op.create_index(
        "ix_execution_run_events_cursor",
        "execution_run_events",
        ["execution_run_id", "sequence"],
    )

    # ── Control commands, so an operator action is auditable and acknowledged ─
    op.create_table(
        "execution_run_commands",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "execution_run_id",
            sa.Integer(),
            sa.ForeignKey("execution_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # The public commandId the control response returns.
        sa.Column("command_key", sa.String(length=40), nullable=False),
        sa.Column("action", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column(
            "requested_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "state", sa.String(length=20), nullable=False, server_default="REQUESTED"
        ),
        # What the operator believed the run version was. A mismatch is a
        # rejection, not a retry.
        sa.Column("expected_run_version", sa.Integer(), nullable=True),
        sa.Column("run_version_at_request", sa.Integer(), nullable=True),
        sa.Column("resulting_state", sa.String(length=30), nullable=True),
        sa.Column("rejection_reason", sa.Text(), nullable=True),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            _in_list("action", CONTROL_ACTIONS), name="ck_execution_run_commands_action"
        ),
        sa.CheckConstraint(
            _in_list("state", COMMAND_STATES), name="ck_execution_run_commands_state"
        ),
        sa.UniqueConstraint("command_key", name="uq_execution_run_commands_key"),
    )
    op.create_index(
        "ix_execution_run_commands_run", "execution_run_commands", ["execution_run_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_execution_run_commands_run", table_name="execution_run_commands")
    op.drop_table("execution_run_commands")

    op.drop_index("ix_execution_run_events_cursor", table_name="execution_run_events")
    op.drop_table("execution_run_events")

    op.drop_index("ix_execution_run_evidence_item", table_name="execution_run_evidence")
    op.drop_index("ix_execution_run_evidence_run", table_name="execution_run_evidence")
    op.drop_table("execution_run_evidence")

    op.drop_index(
        "ix_execution_run_assertions_item", table_name="execution_run_assertions"
    )
    op.drop_table("execution_run_assertions")

    op.drop_index(
        "ix_execution_run_item_steps_item", table_name="execution_run_item_steps"
    )
    op.drop_table("execution_run_item_steps")

    for index in (
        "ix_execution_run_items_run_order",
        "ix_execution_run_items_run_lifecycle",
        "ix_execution_run_items_run_result",
        "ix_execution_run_items_project",
        "ix_execution_run_items_run",
    ):
        op.drop_index(index, table_name="execution_run_items")
    op.drop_table("execution_run_items")

    op.drop_constraint(
        "ck_execution_runs_pending_command", "execution_runs", type_="check"
    )
    op.drop_constraint("ck_execution_runs_outcome", "execution_runs", type_="check")
    op.drop_constraint(
        "ck_execution_runs_lifecycle_state", "execution_runs", type_="check"
    )

    op.drop_index("ix_execution_runs_correlation_id", table_name="execution_runs")
    for column in (
        "correlation_id",
        "execution_purpose",
        "trigger_source",
        "evidence_captured_total",
        "evidence_required_total",
        "parallel_limit",
        "readiness_checked_at",
        "readiness",
        "event_sequence",
        "pending_command_by",
        "pending_command_reason",
        "pending_command",
        "run_version",
        "outcome",
        "lifecycle_state",
    ):
        op.drop_column("execution_runs", column)

    op.drop_index("ix_execution_runs_suite_snapshot_id", table_name="execution_runs")
    op.drop_index("ix_execution_runs_suite_id", table_name="execution_runs")
    op.drop_column("execution_runs", "suite_snapshot_id")
    op.drop_column("execution_runs", "suite_id")
