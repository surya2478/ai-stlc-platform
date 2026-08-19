"""MCP connection registry service (Playwright AI Studio, v1).

Registry + health checks only: "Test Connection" performs a real MCP
handshake (initialize + list_tools) against the registered server and
records status/tool_count. Agents do NOT call these servers during runs
yet — the built-in Playwright Browser MCP stays natively wired into the
planner/discovery agents via mcp_session.py.

Security posture:
  - stdio commands are allowlisted to well-known package launchers
    (npx/uvx/node/python) — registering a connection must not become
    arbitrary-binary execution on the worker, even for project admins.
  - Credentials/env vars are Fernet-encrypted with an HKDF key derived from
    the app secret (same construction as jira_service, own salt/info for
    domain separation) and never leave the server; the API only exposes
    `has_credentials`.
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
from datetime import datetime, timezone

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.automation.mcp_session import PLAYWRIGHT_MCP_BIN, resolve_server_command
from app.config import get_settings
from app.models.mcp_connection import MCPConnection

logger = logging.getLogger(__name__)
settings = get_settings()

TEST_TIMEOUT_SECONDS = 15.0

# Package launchers only — never arbitrary binaries or absolute paths.
# PLAYWRIGHT_MCP_BIN is the one non-launcher here, and only because the image
# installs it: the built-in browser row names it now that the server is
# vendored rather than fetched through `npx` at run time. It is still a bare
# name, so the path-separator check below keeps this from widening into
# "any binary on the worker".
ALLOWED_STDIO_COMMANDS = {"npx", "uvx", "node", "python", "python3", PLAYWRIGHT_MCP_BIN}

_HKDF_SALT = b"stlc-platform-mcp-connection-v1"
_HKDF_INFO = b"mcp-connection-env"


class MCPConnectionValidationError(Exception):
    pass


def _fernet() -> Fernet:
    hkdf = HKDF(algorithm=SHA256(), length=32, salt=_HKDF_SALT, info=_HKDF_INFO)
    key = hkdf.derive(settings.app_secret_key.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_env(env: dict[str, str] | None) -> str | None:
    if not env:
        return None
    return _fernet().encrypt(json.dumps(env).encode("utf-8")).decode("utf-8")


def decrypt_env(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    try:
        raw = _fernet().decrypt(value.encode("utf-8"))
        data = json.loads(raw.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except (InvalidToken, ValueError, json.JSONDecodeError):
        logger.warning("Stored MCP connection env could not be decrypted; treating as empty")
        return {}


def validate_launch_config(*, transport: str, command: str | None, url: str | None) -> None:
    if transport == "stdio":
        if not command:
            raise MCPConnectionValidationError("stdio connections require a command")
        executable = command.strip().split()[0] if command.strip() else ""
        if "/" in executable or "\\" in executable or executable not in ALLOWED_STDIO_COMMANDS:
            raise MCPConnectionValidationError(
                f"Command '{executable}' is not allowed. stdio MCP servers must be launched "
                f"via one of: {', '.join(sorted(ALLOWED_STDIO_COMMANDS))}."
            )
    elif transport == "http":
        if not url or not url.lower().startswith(("http://", "https://")):
            raise MCPConnectionValidationError("http connections require an http(s) URL")
    else:
        raise MCPConnectionValidationError(f"Unknown transport '{transport}'")


async def list_connections(db: AsyncSession, project_id: int) -> list[MCPConnection]:
    result = await db.execute(
        select(MCPConnection)
        .where(MCPConnection.project_id == project_id)
        .order_by(MCPConnection.is_builtin.desc(), MCPConnection.id.asc())
    )
    return list(result.scalars().all())


async def ensure_builtin_browser_connection(db: AsyncSession, project_id: int) -> MCPConnection:
    """Seed (or return) the per-project 'Playwright Browser MCP' row that
    represents the bundled @playwright/mcp the planner/discovery agents use."""
    result = await db.execute(
        select(MCPConnection).where(
            MCPConnection.project_id == project_id,
            MCPConnection.is_builtin.is_(True),
        )
    )
    existing = result.scalars().first()
    resolved, launch_args = resolve_server_command()
    # The row records how the server is launched, but deliberately as the bare
    # executable rather than the absolute path `shutil.which` returned:
    # `validate_launch_config` rejects any command containing a path separator,
    # so storing the resolved path would make this row fail the validation
    # every other row must pass the moment anyone re-saved it.
    command = "npx" if resolved == "npx" else PLAYWRIGHT_MCP_BIN
    if existing:
        # Refresh a row seeded before the server was installed into the image:
        # it still says `npx --yes @playwright/mcp@…`, which is no longer what
        # `_probe_builtin_browser` runs. The row is platform-owned, so
        # correcting it here is cheaper and less error-prone than a migration
        # — and a builtin row that advertises a command nobody executes is a
        # false answer to "how does discovery reach the browser?".
        if existing.command != command or list(existing.args or []) != launch_args:
            existing.command = command
            existing.args = list(launch_args)
            await db.flush()
        return existing
    connection = MCPConnection(
        project_id=project_id,
        name="Playwright Browser MCP",
        connection_type="browser",
        transport="stdio",
        target="Live application browser session",
        command=command,
        args=list(launch_args),
        access_mode="read_write",
        available_to=["planner", "generator", "execution", "healer"],
        status="not_configured",
        is_builtin=True,
    )
    db.add(connection)
    await db.flush()
    return connection


async def _handshake_stdio(connection: MCPConnection) -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parts = (connection.command or "").strip().split()
    args = list(parts[1:]) + [str(a) for a in (connection.args or [])]
    env = decrypt_env(connection.env_encrypted)
    params = StdioServerParameters(command=parts[0], args=args, env=env or None)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return len(tools.tools or [])


async def _handshake_http(connection: MCPConnection) -> int:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    headers = decrypt_env(connection.env_encrypted)
    async with streamablehttp_client(connection.url, headers=headers or None) as (read, write, _sid):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return len(tools.tools or [])


async def _probe_builtin_browser() -> int:
    """The built-in row's health check is a real @playwright/mcp handshake —
    same code path the planner uses, so 'Connected' here means exploration
    will actually work."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    command, launch_args = resolve_server_command()
    params = StdioServerParameters(command=command, args=launch_args + ["--headless"])
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            return len(tools.tools or [])


async def test_connection(db: AsyncSession, connection: MCPConnection) -> MCPConnection:
    """Run the handshake and persist the outcome on the row. Never raises for
    a failing server — failure is a recorded status, not an API error."""
    try:
        if connection.is_builtin:
            probe = _probe_builtin_browser()
        elif connection.transport == "http":
            probe = _handshake_http(connection)
        else:
            probe = _handshake_stdio(connection)
        tool_count = await asyncio.wait_for(probe, timeout=TEST_TIMEOUT_SECONDS)
        connection.status = "connected"
        connection.tool_count = tool_count
        connection.last_error = None
    except asyncio.TimeoutError:
        connection.status = "error"
        connection.last_error = f"Handshake timed out after {int(TEST_TIMEOUT_SECONDS)}s"
    except Exception as exc:
        connection.status = "error"
        connection.last_error = str(exc)[:2000]
        logger.warning("MCP connection %s test failed", connection.id, exc_info=True)
    connection.last_checked_at = datetime.now(timezone.utc)
    await db.flush()
    return connection
