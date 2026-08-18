"""067 - Test Automation Studio: score coverage over acceptance criteria

Screen 1 reported coverage as a share of requirements, which made the figure a
function of how the model chose to split the document rather than of how much
was tested. A BRD that extracts as a single requirement can only ever score 0,
50 or 100 percent, so one untested acceptance criterion out of five was shown
as a 50% coverage gap — while the same two documents assessed on another
project reported 100% and no gaps at all.

Adds the counts the criterion-level score is computed from:

  tas_coverage_assessments  total_criteria, covered_criteria — the assessment's
                            denominator and numerator, so a stored percent can
                            be explained after the fact
  tas_derived_requirements  total_criteria, covered_criteria — the same counts
                            per requirement, so the grid can say "4 of 5"
                            instead of only "partially covered"

Purely additive, and existing rows keep the percent they were recorded with:
the new columns default to 0, which the service reads as "this assessment
predates criterion scoring" and leaves its percent alone.

Revision ID: 067
Revises: 066
Create Date: 2026-08-18
"""
from alembic import op
import sqlalchemy as sa

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


_COLUMNS = ("total_criteria", "covered_criteria")
_TABLES = ("tas_coverage_assessments", "tas_derived_requirements")


def upgrade() -> None:
    for table in _TABLES:
        for column in _COLUMNS:
            op.add_column(
                table,
                sa.Column(
                    column,
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )


def downgrade() -> None:
    for table in _TABLES:
        for column in _COLUMNS:
            op.drop_column(table, column)
