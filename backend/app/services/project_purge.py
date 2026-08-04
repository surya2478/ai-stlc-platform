"""Deterministic ordering for deleting a project and everything scoped to it.

Deleting a project used to run through a hand-maintained list of models. That
list rotted: every new project-scoped table had to be remembered, and the order
had to keep satisfying every foreign key that has no ``ON DELETE CASCADE``. It
eventually broke on ``fk_test_cases_last_execution_run_id`` — ``execution_runs``
was deleted before ``test_cases``, which still pointed at it.

Instead of maintaining that list by hand, derive it from the live schema:

* Every table with a single-column foreign key to ``projects`` is project
  scoped, and its rows go with the project. The exception is ``ON DELETE SET
  NULL``, which explicitly means "keep the row, forget the project".
* Deletes are ordered child-before-parent across every foreign key the database
  will *not* resolve on its own (``NO ACTION`` / ``RESTRICT``). Cascading keys
  need no ordering — the database follows them itself.

Tables that hang off a project-scoped table without a ``project_id`` of their
own are removed by their own parent's ``ON DELETE CASCADE``.

Identifiers come from ``pg_catalog`` via ``::regclass::text``, so they are
already quoted and schema-qualified by Postgres — never interpolated user input.
"""
import logging
from collections import defaultdict

from sqlalchemy import TextClause, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Single-column foreign keys pointing at projects.id, with the referencing
# column and what the database does when the project row goes.
_PROJECT_SCOPED_TABLES = text(
    """
    SELECT c.conrelid::regclass::text AS child_table,
           quote_ident(a.attname)     AS child_column,
           c.confdeltype              AS del_type
    FROM pg_constraint c
    JOIN pg_attribute a ON a.attrelid = c.conrelid AND a.attnum = c.conkey[1]
    WHERE c.contype = 'f'
      AND c.confrelid = 'projects'::regclass
      AND array_length(c.conkey, 1) = 1
    """
)

# Foreign keys the database will not resolve for us: the referencing rows have
# to be gone before the referenced rows are deleted.
_BLOCKING_EDGES = text(
    """
    SELECT c.conrelid::regclass::text  AS child_table,
           c.confrelid::regclass::text AS parent_table
    FROM pg_constraint c
    WHERE c.contype = 'f'
      AND c.confdeltype IN ('a', 'r')
      AND c.conrelid <> c.confrelid
    """
)

_SET_NULL = "n"


def _as_str(value: object) -> str:
    """asyncpg returns Postgres ``"char"`` columns as bytes."""
    return value.decode() if isinstance(value, (bytes, bytearray)) else str(value)


def _order_children_first(tables: set[str], edges: list[tuple[str, str]]) -> list[str]:
    """Kahn sort so every referencing table precedes the table it references."""
    parents_of: dict[str, set[str]] = defaultdict(set)
    children_of: dict[str, set[str]] = defaultdict(set)
    for child, parent in edges:
        if child in tables and parent in tables and parent not in parents_of[child]:
            parents_of[child].add(parent)
            children_of[parent].add(child)

    ordered: list[str] = []
    # Sort by name so the emitted plan is stable run to run.
    ready = sorted(t for t in tables if not children_of[t])
    while ready:
        table = ready.pop(0)
        ordered.append(table)
        for parent in sorted(parents_of[table]):
            children_of[parent].discard(table)
            if not children_of[parent]:
                ready.append(parent)
        ready.sort()

    remaining = sorted(tables - set(ordered))
    if remaining:
        # A cycle of non-cascading foreign keys. Nothing here can order it
        # correctly, so emit the rest and let the database report the specific
        # constraint rather than silently skipping rows.
        logger.warning(
            "project purge: foreign key cycle among %s; deleting in name order",
            ", ".join(remaining),
        )
        ordered.extend(remaining)
    return ordered


async def project_purge_plan(db: AsyncSession) -> list[TextClause]:
    """Statements that delete a project and all of its rows, in a safe order.

    Each statement takes a single ``:project_id`` bind parameter. The last one
    deletes the project row itself.
    """
    scoped = (await db.execute(_PROJECT_SCOPED_TABLES)).all()
    columns: dict[str, list[str]] = defaultdict(list)
    for child_table, child_column, del_type in scoped:
        if _as_str(del_type) == _SET_NULL:
            continue  # row outlives the project by design
        columns[child_table].append(child_column)

    edges = [
        (child, parent)
        for child, parent in (await db.execute(_BLOCKING_EDGES)).all()
    ]

    plan: list[TextClause] = []
    for table in _order_children_first(set(columns), edges):
        for column in sorted(columns[table]):
            plan.append(text(f"DELETE FROM {table} WHERE {column} = :project_id"))
    plan.append(text("DELETE FROM projects WHERE id = :project_id"))
    return plan
