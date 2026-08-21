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
* A row-preserving key (``SET NULL`` / ``SET DEFAULT``) is ordered against every
  table that *cascades* into the one it points at, though not against that table
  itself.

  That last rule is the one this file was missing, and without it no project
  holding refined test cases could be deleted at all.
  ``tas_refined_test_cases`` points at ``tas_source_test_cases`` with ``ON
  DELETE SET NULL``, and ``tas_intake_batches`` cascades into that same table.
  Nothing ordered the batches, so the plan sorted the three alphabetically and
  deleted the batches first. Postgres then ran the cascade and the set-null over
  overlapping rows inside one statement and aborted with a foreign key violation
  naming a parent its own cascade had just removed.

  Ordering the row-preserving keys against their own parent as well looks like
  the simpler rule and is not: those keys criss-cross the core schema, and
  adding them puts sixteen tables into a single cycle. The name-order fallback
  that follows a cycle then deletes ``execution_runs`` before ``test_cases`` —
  the original bug, back again. Ordering only against the cascade keeps the
  graph acyclic.

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

# Every foreign key between two different tables, with what the database does
# to the referencing rows when the referenced row goes. Self-references are
# excluded: a table cannot be ordered against itself, and one DELETE clears
# both ends.
_FOREIGN_KEYS = text(
    """
    SELECT c.conrelid::regclass::text  AS child_table,
           c.confrelid::regclass::text AS parent_table,
           c.confdeltype               AS del_type
    FROM pg_constraint c
    WHERE c.contype = 'f'
      AND c.conrelid <> c.confrelid
    """
)

# Keys the database will not resolve for us: it aborts the delete instead, so
# the referencing rows have to be gone first.
_BLOCKING = frozenset({"a", "r"})

_CASCADE = "c"
_SET_NULL = "n"


def _as_str(value: object) -> str:
    """asyncpg returns Postgres ``"char"`` columns as bytes."""
    return value.decode() if isinstance(value, (bytes, bytearray)) else str(value)


def _cascade_reach(cascades: list[tuple[str, str]]) -> dict[str, set[str]]:
    """For each table, every table whose deletion also removes its rows.

    Follows cascade edges upwards and transitively: if deleting a batch deletes
    a source row, and deleting a project deletes the batch, then both are in the
    source table's reach. A cascade cycle is walked once and left at that.
    """
    parents_of: dict[str, set[str]] = defaultdict(set)
    for child, parent in cascades:
        parents_of[child].add(parent)

    reach: dict[str, set[str]] = {}
    for table in parents_of:
        seen: set[str] = set()
        stack = list(parents_of[table])
        while stack:
            parent = stack.pop()
            if parent in seen:
                continue
            seen.add(parent)
            stack.extend(parents_of.get(parent, ()))
        reach[table] = seen
    return reach


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

    foreign_keys = [
        (child, parent, _as_str(del_type))
        for child, parent, del_type in (await db.execute(_FOREIGN_KEYS)).all()
    ]
    reach = _cascade_reach(
        [(child, parent) for child, parent, d in foreign_keys if d == _CASCADE]
    )

    edges = [(child, parent) for child, parent, d in foreign_keys if d in _BLOCKING]

    # A row-preserving key (SET NULL, SET DEFAULT) needs no ordering against the
    # table it points at: rewriting the column is exactly what the database will
    # do, and it does it correctly. It does need ordering against whatever
    # *cascades* into that table, because then both fire over the same rows
    # inside one statement and the rewrite loses. Ordering the row-preserving
    # keys directly instead would put sixteen core tables in one cycle; this
    # keeps the graph acyclic and still empties the referencing table first.
    for child, parent, del_type in foreign_keys:
        if del_type == _CASCADE:
            continue
        edges.extend((child, table) for table in reach.get(parent, ()))

    plan: list[TextClause] = []
    for table in _order_children_first(set(columns), edges):
        for column in sorted(columns[table]):
            plan.append(text(f"DELETE FROM {table} WHERE {column} = :project_id"))
    plan.append(text("DELETE FROM projects WHERE id = :project_id"))
    return plan
