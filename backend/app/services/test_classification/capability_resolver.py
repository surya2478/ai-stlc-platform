"""Resolves adapter/validator keys against the real, project-scoped
MCPConnection registry — never a static list embedded in Python or the
frontend (constraint: "No static application, adapter or MCP list is
embedded in frontend logic"; the backend mirrors that for adapters too).

A validator/adapter key (e.g. "PLAYWRIGHT_MCP", "OMS_MCP", "BILLING_MCP")
is resolvable only if some MCPConnection row in the project carries a
matching `capability_key`. No match => UNSUPPORTED (nothing in this
project declares it); a match with status != "connected" => NOT_CONFIGURED.
Nothing is ever silently treated as REAL/operational.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.mcp_connection import MCPConnection

CapabilityMaturity = str  # REAL | MOCK | VIRTUALIZED | RECORDED | NOT_CONFIGURED | UNSUPPORTED

# The one built-in exception: Playwright Browser MCP is seeded per-project
# (see mcp_connection_service.py) and natively wired into the planner even
# before an admin tags it with a capability_key — so it resolves by
# is_builtin fallback in addition to capability_key matching.
BUILTIN_PRIMARY_ADAPTER_KEY = "PLAYWRIGHT_MCP"


@dataclass
class CapabilityStatus:
    key: str
    maturity: CapabilityMaturity
    mcp_connection_id: int | None
    detail: str


async def resolve_capabilities(
    db: AsyncSession, *, project_id: int, keys: list[str]
) -> dict[str, CapabilityStatus]:
    """Resolve a set of adapter/validator keys for one project in a single query."""
    unique_keys = sorted({k for k in keys if k})
    resolved: dict[str, CapabilityStatus] = {}
    if not unique_keys:
        return resolved

    result = await db.execute(
        select(MCPConnection).where(
            MCPConnection.project_id == project_id,
            MCPConnection.capability_key.in_(unique_keys),
        )
    )
    by_key = {row.capability_key: row for row in result.scalars().all()}

    builtin_result = None
    if BUILTIN_PRIMARY_ADAPTER_KEY in unique_keys and BUILTIN_PRIMARY_ADAPTER_KEY not in by_key:
        builtin_res = await db.execute(
            select(MCPConnection).where(
                MCPConnection.project_id == project_id,
                MCPConnection.is_builtin.is_(True),
                MCPConnection.connection_type == "browser",
            )
        )
        builtin_result = builtin_res.scalars().first()

    for key in unique_keys:
        row = by_key.get(key) or (builtin_result if key == BUILTIN_PRIMARY_ADAPTER_KEY else None)
        if row is None:
            resolved[key] = CapabilityStatus(
                key=key, maturity="UNSUPPORTED", mcp_connection_id=None,
                detail=f"No MCP connection in this project declares capability_key '{key}'.",
            )
            continue
        if row.status == "connected":
            resolved[key] = CapabilityStatus(
                key=key, maturity="REAL", mcp_connection_id=row.id, detail=f"Connected via '{row.name}'.",
            )
        else:
            resolved[key] = CapabilityStatus(
                key=key, maturity="NOT_CONFIGURED", mcp_connection_id=row.id,
                detail=f"'{row.name}' is registered but status is '{row.status}'.",
            )
    return resolved


def unavailable_keys(resolved: dict[str, CapabilityStatus]) -> list[str]:
    return [key for key, status in resolved.items() if status.maturity not in {"REAL", "MOCK", "VIRTUALIZED", "RECORDED"}]
