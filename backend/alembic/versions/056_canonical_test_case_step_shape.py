"""056 - Normalize test_cases.steps to the canonical step shape

Steps have been persisted in two shapes. The canonical one —
{step_number, action, expected_result} — is what the test case agent, the
importer and the test-case editor write. Playwright Studio's plan approval
wrote {action, expected} instead: the planner has no per-step expectation
(planner_agent.PlannedStep is action/element/value/description), so that key
was invented at the write site and no other producer or consumer uses it.

Consumers that looked for `expected_result` therefore found nothing, and the
frontend — whose TestCase type promises `expected_result: string`, so the
compiler never flagged the difference — threw "Cannot read properties of
undefined (reading 'trim')" and took the entire /test-cases page down for any
project holding a Studio-approved test case (observed live on project 12).

studio_service now writes the canonical shape, so this migration is only about
rows already on disk. Surveyed before writing it, across every row with steps:

    action,expected_result,step_number    61 rows   (already canonical)
    action,expected                       39 rows   (Studio)

with no non-array `steps`, no non-object step elements, no row carrying both
keys, and — the part that makes this lossless — not one non-empty `expected`
value anywhere. Nothing is being discarded; a key nothing reads is being
renamed to the one everything reads.

The rewrite MERGES onto the original step object (`e - 'expected' || ...`)
rather than rebuilding it from three fields, so any key this database has not
seen survives the migration on another environment. `step_number` is taken
from WITH ORDINALITY — array position is the only ordering these rows have
ever had, and an existing step_number is preserved rather than renumbered.

Not reversible in a meaningful sense: the down migration would have to invent
which rows once used the broken key, and reintroducing it would only break the
page again. downgrade() is therefore a no-op — the canonical shape is readable
by every version of the code, including the one before this fix.
"""
from alembic import op

revision = "056"
down_revision = "055"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE test_cases AS tc
        SET steps = rebuilt.steps
        FROM (
            SELECT
                t.id,
                jsonb_agg(
                    (e.value - 'expected') || jsonb_build_object(
                        'step_number', COALESCE((e.value->>'step_number')::int, e.ordinality::int),
                        'action', COALESCE(e.value->>'action', ''),
                        'expected_result', COALESCE(
                            e.value->>'expected_result', e.value->>'expected', ''
                        )
                    )
                    ORDER BY e.ordinality
                ) AS steps
            FROM test_cases t,
                 LATERAL jsonb_array_elements(t.steps) WITH ORDINALITY AS e(value, ordinality)
            WHERE t.steps IS NOT NULL
              AND jsonb_typeof(t.steps) = 'array'
              AND jsonb_array_length(t.steps) > 0
              -- Only rows that actually deviate. A step is canonical when it
              -- carries all three keys and no stray 'expected'.
              AND EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(t.steps) s
                  WHERE jsonb_typeof(s) = 'object'
                    AND (
                        s ? 'expected'
                        OR NOT (s ? 'expected_result')
                        OR NOT (s ? 'step_number')
                        OR NOT (s ? 'action')
                    )
              )
              -- A non-object element cannot be merged onto; leave those rows
              -- entirely alone rather than half-rewriting them.
              AND NOT EXISTS (
                  SELECT 1
                  FROM jsonb_array_elements(t.steps) s
                  WHERE jsonb_typeof(s) <> 'object'
              )
            GROUP BY t.id
        ) AS rebuilt
        WHERE tc.id = rebuilt.id
        """
    )


def downgrade() -> None:
    """No-op. See the module docstring: the canonical shape is readable by
    every version of the code, and restoring the broken key would require
    inventing which rows once carried it."""
