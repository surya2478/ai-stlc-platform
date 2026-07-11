"""Pydantic schemas for the MCP connection registry endpoints.

`env` (credentials/headers) is write-only: accepted on create/update,
stored encrypted, and never echoed back — responses expose only
`has_credentials`.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

AGENT_ROLES = {"planner", "generator", "execution", "healer"}


class MCPConnectionCreate(BaseModel):
    project_id: int
    name: str = Field(min_length=1, max_length=200)
    connection_type: str = Field(default="custom", pattern="^(browser|api|db|kafka|application|custom)$")
    transport: str = Field(default="stdio", pattern="^(stdio|http)$")
    target: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=200)
    args: list[str] = Field(default_factory=list, max_length=30)
    url: str | None = Field(default=None, max_length=2000)
    env: dict[str, str] | None = None
    access_mode: str = Field(default="read_only", pattern="^(read_only|read_write)$")
    available_to: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        self.available_to = [a for a in self.available_to if a in AGENT_ROLES]


class MCPConnectionUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    connection_type: str | None = Field(default=None, pattern="^(browser|api|db|kafka|application|custom)$")
    transport: str | None = Field(default=None, pattern="^(stdio|http)$")
    target: str | None = Field(default=None, max_length=500)
    command: str | None = Field(default=None, max_length=200)
    args: list[str] | None = Field(default=None, max_length=30)
    url: str | None = Field(default=None, max_length=2000)
    # None = leave stored credentials untouched; {} = clear them.
    env: dict[str, str] | None = None
    access_mode: str | None = Field(default=None, pattern="^(read_only|read_write)$")
    available_to: list[str] | None = None


class MCPConnectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    connection_type: str
    transport: str
    target: str | None = None
    command: str | None = None
    args: list | None = None
    url: str | None = None
    access_mode: str
    available_to: list | None = None
    status: str
    tool_count: int | None = None
    last_checked_at: datetime | None = None
    last_error: str | None = None
    is_builtin: bool
    has_credentials: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None


def connection_to_out(connection) -> MCPConnectionOut:
    out = MCPConnectionOut.model_validate(connection)
    out.has_credentials = bool(connection.env_encrypted)
    return out


class MCPConnectionTestResult(BaseModel):
    id: int
    name: str
    status: str
    tool_count: int | None = None
    last_error: str | None = None


class MCPConnectionTestAllResponse(BaseModel):
    results: list[MCPConnectionTestResult]
    connected_count: int
    error_count: int
