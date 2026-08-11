"""064 - TAS: give uploaded test cases an identity

Screen 1 already extracts the test cases out of an uploaded TC sheet, but it
only kept them inside `tas_coverage_assessments.extracted_test_cases`. Nothing
could reference a JSONB element, so Screen 2's refine path could reach an
uploaded test case only by matching its display ID against the platform
`test_cases` table. A project that never imported its test cases into the
platform — the normal case for this module — therefore fell through to the
"create from requirement" path and lost the ID and name from the sheet.

This adds `tas_source_test_cases` (one row per test case read off a sheet) and
points `tas_refined_test_cases` at it, so an uploaded test case can be refined
in place while keeping its ID and title.

Revision ID: 064
Revises: 063
Create Date: 2026-08-11
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "064"
down_revision = "063"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tas_source_test_cases",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column(
            "project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "batch_id",
            sa.Integer(),
            sa.ForeignKey("tas_intake_batches.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assessment_id",
            sa.Integer(),
            sa.ForeignKey("tas_coverage_assessments.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("tc_display_id", sa.String(length=100), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column(
            "steps", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
        ),
        sa.Column(
            "source_document_id",
            sa.Integer(),
            sa.ForeignKey("uploaded_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source_ref", sa.Text(), nullable=True),
        sa.Column(
            "matched_platform_test_case_id",
            sa.Integer(),
            sa.ForeignKey("test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
        # Scoped to the batch, not the project: two intakes may legitimately
        # carry the same sheet ID, and re-assessing a batch must update its own
        # rows in place rather than collide with another batch's.
        sa.UniqueConstraint("batch_id", "tc_display_id", name="uq_tas_source_test_case_key"),
    )
    op.create_index("ix_tas_source_test_cases_project_id", "tas_source_test_cases", ["project_id"])
    op.create_index("ix_tas_source_test_cases_batch_id", "tas_source_test_cases", ["batch_id"])
    op.create_index("ix_tas_source_test_cases_assessment_id", "tas_source_test_cases", ["assessment_id"])
    op.create_index("ix_tas_source_test_cases_tc_display_id", "tas_source_test_cases", ["tc_display_id"])
    op.create_index(
        "ix_tas_source_test_cases_source_document_id", "tas_source_test_cases", ["source_document_id"]
    )
    op.create_index(
        "ix_tas_source_test_cases_matched_platform_test_case_id",
        "tas_source_test_cases",
        ["matched_platform_test_case_id"],
    )

    op.add_column(
        "tas_refined_test_cases",
        sa.Column(
            "source_uploaded_test_case_id",
            sa.Integer(),
            sa.ForeignKey("tas_source_test_cases.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_tas_refined_test_cases_source_uploaded_test_case_id",
        "tas_refined_test_cases",
        ["source_uploaded_test_case_id"],
    )

    # `imported` joins the origin vocabulary: refined from an uploaded sheet
    # rather than from a platform row (`existing`) or a gap requirement
    # (`derived`).
    op.drop_constraint("ck_tas_refined_tc_origin", "tas_refined_test_cases", type_="check")
    op.create_check_constraint(
        "ck_tas_refined_tc_origin",
        "tas_refined_test_cases",
        "origin IN ('existing','imported','derived')",
    )

    # Backfill from the assessments that already ran. Without this a project
    # that has already assessed its documents would have to re-run the
    # assessment — an LLM job costing minutes — purely to see test cases the
    # platform already extracted and stored. Only current assessments are read;
    # superseded ones describe a state the user has already replaced.
    #
    # DISTINCT ON keeps the first row for a duplicated ID, matching what the
    # service does and what the unique constraint requires. Entries with no
    # title are skipped: they carry nothing worth refining.
    op.execute(
        """
        INSERT INTO tas_source_test_cases (
            project_id, batch_id, assessment_id, tc_display_id, title, summary,
            steps, source_document_id, source_ref, matched_platform_test_case_id,
            created_by, updated_by
        )
        SELECT DISTINCT ON (a.batch_id, lower(trim(both from tc.display_id)))
            a.project_id,
            a.batch_id,
            a.id,
            trim(both from tc.display_id),
            left(trim(both from tc.title), 500),
            tc.summary,
            COALESCE(tc.steps, '[]'::jsonb),
            tc.source_document_id,
            tc.source_ref,
            (
                SELECT pc.id FROM test_cases pc
                WHERE pc.project_id = a.project_id
                  AND NOT pc.is_deleted
                  AND lower(trim(both from pc.test_case_id))
                      = lower(trim(both from tc.display_id))
                LIMIT 1
            ),
            a.created_by,
            a.created_by
        FROM tas_coverage_assessments a
        CROSS JOIN LATERAL (
            SELECT
                NULLIF(trim(both from e ->> 'test_case_id'), '') AS display_id,
                NULLIF(trim(both from e ->> 'title'), '')         AS title,
                e ->> 'summary'                                   AS summary,
                CASE
                    WHEN jsonb_typeof(e -> 'steps') = 'array' THEN e -> 'steps'
                    ELSE '[]'::jsonb
                END                                               AS steps,
                CASE
                    WHEN (e ->> 'source_document_id') ~ '^[0-9]+$'
                    THEN (e ->> 'source_document_id')::int
                END                                               AS source_document_id,
                e ->> 'source_ref'                                AS source_ref
            FROM jsonb_array_elements(a.extracted_test_cases) AS e
        ) tc
        WHERE a.is_current
          AND tc.display_id IS NOT NULL
          AND tc.title IS NOT NULL
        ORDER BY a.batch_id, lower(trim(both from tc.display_id)), a.id DESC
        ON CONFLICT (batch_id, tc_display_id) DO NOTHING
        """
    )


def downgrade() -> None:
    # Rows refined from an uploaded sheet have no representation in the old
    # vocabulary. They are reclassified as `derived` — which is what they would
    # have been before this migration existed — so the narrower constraint can
    # be restored without deleting a user's generated test cases.
    op.execute(
        "UPDATE tas_refined_test_cases SET origin = 'derived' WHERE origin = 'imported'"
    )
    op.drop_constraint("ck_tas_refined_tc_origin", "tas_refined_test_cases", type_="check")
    op.create_check_constraint(
        "ck_tas_refined_tc_origin",
        "tas_refined_test_cases",
        "origin IN ('existing','derived')",
    )

    op.drop_index(
        "ix_tas_refined_test_cases_source_uploaded_test_case_id", table_name="tas_refined_test_cases"
    )
    op.drop_column("tas_refined_test_cases", "source_uploaded_test_case_id")
    op.drop_table("tas_source_test_cases")
