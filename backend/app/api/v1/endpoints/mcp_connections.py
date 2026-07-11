"""MCP connection registry endpoints (Playwright AI Studio).

Listing requires project access; mutating and testing require
MANAGE_PROJECT — registering an MCP connection points platform agents at
external infrastructure, which is admin-level configuration, and "Test
Connection" launches the registered server process/URL for the handshake.
"""
from fastapi import APIRouter, HTTPException, Query

from app.api.deps import CurrentUser, DBSession, require_permission, require_project_access
from app.models.mcp_connection import MCPConnection
from app.schemas.mcp_connection import (
    MCPConnectionCreate,
    MCPConnectionOut,
    MCPConnectionTestAllResponse,
    MCPConnectionTestResult,
    MCPConnectionUpdate,
    connection_to_out,
)
from app.services import mcp_connection_service
from app.services.mcp_connection_service import MCPConnectionValidationError
from app.services.rbac_service import MANAGE_PROJECT

router = APIRouter()


async def _get_connection_or_404(db, connection_id: int) -> MCPConnection:
    connection = await db.get(MCPConnection, connection_id)
    if connection is None:
        raise HTTPException(status_code=404, detail="MCP connection not found")
    return connection


@router.get("", response_model=list[MCPConnectionOut])
async def list_mcp_connections(
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(...),
):
    await require_project_access(project_id, current_user, db)
    # The built-in Playwright Browser MCP row is seeded on first listing so
    # the Studio's connections table always shows the browser lane.
    await mcp_connection_service.ensure_builtin_browser_connection(db, project_id)
    await db.commit()
    connections = await mcp_connection_service.list_connections(db, project_id)
    return [connection_to_out(c) for c in connections]


@router.post("", response_model=MCPConnectionOut, status_code=201)
async def create_mcp_connection(body: MCPConnectionCreate, db: DBSession, current_user: CurrentUser):
    await require_permission(MANAGE_PROJECT, body.project_id, current_user, db)
    try:
        mcp_connection_service.validate_launch_config(
            transport=body.transport, command=body.command, url=body.url
        )
    except MCPConnectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    connection = MCPConnection(
        project_id=body.project_id,
        created_by=current_user.id,
        name=body.name,
        connection_type=body.connection_type,
        transport=body.transport,
        target=body.target,
        command=body.command,
        args=body.args or None,
        url=body.url,
        env_encrypted=mcp_connection_service.encrypt_env(body.env),
        access_mode=body.access_mode,
        available_to=body.available_to or None,
        status="not_configured",
        is_builtin=False,
    )
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    return connection_to_out(connection)


@router.patch("/{connection_id}", response_model=MCPConnectionOut)
async def update_mcp_connection(
    connection_id: int, body: MCPConnectionUpdate, db: DBSession, current_user: CurrentUser
):
    connection = await _get_connection_or_404(db, connection_id)
    await require_permission(MANAGE_PROJECT, connection.project_id, current_user, db)
    if connection.is_builtin:
        raise HTTPException(status_code=422, detail="The built-in Playwright Browser MCP cannot be edited.")

    updates = body.model_dump(exclude_unset=True)
    env = updates.pop("env", None)
    for field, value in updates.items():
        setattr(connection, field, value)
    if env is not None:
        connection.env_encrypted = mcp_connection_service.encrypt_env(env)
    try:
        mcp_connection_service.validate_launch_config(
            transport=connection.transport, command=connection.command, url=connection.url
        )
    except MCPConnectionValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # Config changed — the previous health-check verdict no longer applies.
    connection.status = "not_configured"
    connection.tool_count = None
    connection.last_error = None
    await db.commit()
    await db.refresh(connection)
    return connection_to_out(connection)


@router.delete("/{connection_id}", status_code=204)
async def delete_mcp_connection(connection_id: int, db: DBSession, current_user: CurrentUser):
    connection = await _get_connection_or_404(db, connection_id)
    await require_permission(MANAGE_PROJECT, connection.project_id, current_user, db)
    if connection.is_builtin:
        raise HTTPException(status_code=422, detail="The built-in Playwright Browser MCP cannot be deleted.")
    await db.delete(connection)
    await db.commit()


@router.post("/{connection_id}/test", response_model=MCPConnectionOut)
async def test_mcp_connection(connection_id: int, db: DBSession, current_user: CurrentUser):
    connection = await _get_connection_or_404(db, connection_id)
    await require_permission(MANAGE_PROJECT, connection.project_id, current_user, db)
    connection = await mcp_connection_service.test_connection(db, connection)
    await db.commit()
    await db.refresh(connection)
    return connection_to_out(connection)


@router.post("/test-all", response_model=MCPConnectionTestAllResponse)
async def test_all_mcp_connections(
    db: DBSession,
    current_user: CurrentUser,
    project_id: int = Query(...),
):
    await require_permission(MANAGE_PROJECT, project_id, current_user, db)
    await mcp_connection_service.ensure_builtin_browser_connection(db, project_id)
    connections = await mcp_connection_service.list_connections(db, project_id)
    results = []
    for connection in connections:
        connection = await mcp_connection_service.test_connection(db, connection)
        results.append(MCPConnectionTestResult(
            id=connection.id,
            name=connection.name,
            status=connection.status,
            tool_count=connection.tool_count,
            last_error=connection.last_error,
        ))
    await db.commit()
    return MCPConnectionTestAllResponse(
        results=results,
        connected_count=sum(1 for r in results if r.status == "connected"),
        error_count=sum(1 for r in results if r.status == "error"),
    )
