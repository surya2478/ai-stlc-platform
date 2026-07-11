"""M3 (Playwright AI Studio): MCP connection registry — encryption
round-trip, stdio command allowlist, health-check outcome persistence, and
endpoint wiring (create/update/delete guards, credential redaction). The
real MCP handshake is exercised live in M5; here it's mocked."""
from types import SimpleNamespace

import anyio
import pytest
from fastapi.testclient import TestClient

import app.services.mcp_connection_service as svc
from app.api.deps import require_user
from app.database import get_db
from app.main import app
from app.models.mcp_connection import MCPConnection
from app.models.project import Project
from app.models.user import User
from app.services.mcp_connection_service import (
    MCPConnectionValidationError,
    decrypt_env,
    encrypt_env,
    validate_launch_config,
)


class _ScalarsResult:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class _ExecResult:
    def __init__(self, *, single=None, many=None):
        self._single = single
        self._many = many if many is not None else []

    def scalar_one_or_none(self):
        return self._single

    def scalars(self):
        return _ScalarsResult(self._many)


class _FakeDB:
    def __init__(self, get_map=None, execute_queue=None):
        self.get_map = dict(get_map or {})
        self.execute_queue = list(execute_queue or [])
        self.added = []
        self.deleted = []
        self.next_id = 1000
        self.commits = 0

    def add(self, obj):
        if getattr(obj, "id", None) is None:
            obj.id = self.next_id
            self.next_id += 1
        self.added.append(obj)
        self.get_map[(type(obj), obj.id)] = obj

    async def delete(self, obj):
        self.deleted.append(obj)

    async def flush(self):
        return None

    async def commit(self):
        self.commits += 1

    async def refresh(self, _obj):
        return None

    async def get(self, model, object_id):
        return self.get_map.get((model, object_id))

    async def execute(self, _stmt):
        return self.execute_queue.pop(0)


async def _owner_user():
    return User(
        id=1, email="owner@example.com", full_name="Owner", hashed_password="x",
        role="qa_engineer", is_active=True, is_superuser=False,
    )


def _override(db):
    async def fake_db():
        yield db

    app.dependency_overrides[get_db] = fake_db
    app.dependency_overrides[require_user] = _owner_user


def _clear():
    app.dependency_overrides.clear()


def _project():
    return Project(id=1, owner_id=1, name="Project")


def _connection(**overrides):
    defaults = dict(
        id=10, project_id=1, name="Order API MCP", connection_type="api",
        transport="stdio", command="npx", args=["-y", "@example/api-mcp"],
        access_mode="read_only", status="not_configured", is_builtin=False,
    )
    defaults.update(overrides)
    return MCPConnection(**defaults)


# ── Encryption round-trip ────────────────────────────────────────────────────

def test_env_encryption_round_trip():
    env = {"API_KEY": "secret-value", "DB_URL": "postgres://x"}
    token = encrypt_env(env)
    assert token is not None
    assert "secret-value" not in token
    assert decrypt_env(token) == env


def test_env_encryption_handles_empty_and_garbage():
    assert encrypt_env(None) is None
    assert encrypt_env({}) is None
    assert decrypt_env(None) == {}
    assert decrypt_env("not-a-fernet-token") == {}


# ── stdio command allowlist ──────────────────────────────────────────────────

def test_validate_launch_config_allows_known_launchers():
    for command in ("npx", "uvx", "node", "python3"):
        validate_launch_config(transport="stdio", command=f"{command} something", url=None)


@pytest.mark.parametrize("command", [
    "/bin/bash", "bash", "rm -rf /", "C:\\evil.exe", "./local-binary", "", None,
])
def test_validate_launch_config_rejects_arbitrary_binaries(command):
    with pytest.raises(MCPConnectionValidationError):
        validate_launch_config(transport="stdio", command=command, url=None)


def test_validate_launch_config_http_requires_http_url():
    validate_launch_config(transport="http", command=None, url="https://mcp.example.com")
    with pytest.raises(MCPConnectionValidationError):
        validate_launch_config(transport="http", command=None, url="ftp://mcp.example.com")


# ── Health check persistence ─────────────────────────────────────────────────

def test_test_connection_records_success(monkeypatch):
    connection = _connection()
    db = _FakeDB()

    async def fake_handshake(_connection):
        return 7

    monkeypatch.setattr(svc, "_handshake_stdio", fake_handshake)

    async def run():
        return await svc.test_connection(db, connection)

    anyio.run(run)
    assert connection.status == "connected"
    assert connection.tool_count == 7
    assert connection.last_error is None
    assert connection.last_checked_at is not None


def test_test_connection_records_failure_without_raising(monkeypatch):
    connection = _connection()
    db = _FakeDB()

    async def fake_handshake(_connection):
        raise RuntimeError("connection refused")

    monkeypatch.setattr(svc, "_handshake_stdio", fake_handshake)

    async def run():
        return await svc.test_connection(db, connection)

    anyio.run(run)
    assert connection.status == "error"
    assert "connection refused" in connection.last_error


def test_builtin_row_uses_playwright_probe(monkeypatch):
    connection = _connection(is_builtin=True, name="Playwright Browser MCP")
    db = _FakeDB()
    called = []

    async def fake_probe():
        called.append(True)
        return 21

    monkeypatch.setattr(svc, "_probe_builtin_browser", fake_probe)

    async def run():
        return await svc.test_connection(db, connection)

    anyio.run(run)
    assert called == [True]
    assert connection.status == "connected"
    assert connection.tool_count == 21


# ── Endpoints ────────────────────────────────────────────────────────────────

URL = "/api/v1/mcp-connections"


def test_create_connection_encrypts_env_and_redacts_response():
    db = _FakeDB(execute_queue=[_ExecResult(single=_project())])
    _override(db)
    try:
        response = TestClient(app).post(URL, json={
            "project_id": 1, "name": "Order DB MCP", "connection_type": "db",
            "transport": "stdio", "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-postgres"],
            "env": {"PGPASSWORD": "super-secret"},
            "access_mode": "read_only", "available_to": ["planner", "bogus-role"],
        })
    finally:
        _clear()
    assert response.status_code == 201
    body = response.json()
    assert body["has_credentials"] is True
    assert "env" not in body and "env_encrypted" not in body
    assert body["available_to"] == ["planner"]  # unknown roles filtered
    created = db.added[0]
    assert "super-secret" not in (created.env_encrypted or "")
    assert decrypt_env(created.env_encrypted) == {"PGPASSWORD": "super-secret"}


def test_create_connection_rejects_disallowed_command():
    db = _FakeDB(execute_queue=[_ExecResult(single=_project())])
    _override(db)
    try:
        response = TestClient(app).post(URL, json={
            "project_id": 1, "name": "Evil", "transport": "stdio", "command": "bash -c 'x'",
        })
    finally:
        _clear()
    assert response.status_code == 422
    assert "not allowed" in response.json()["detail"]


def test_builtin_connection_cannot_be_edited_or_deleted():
    builtin = _connection(id=5, is_builtin=True)
    db = _FakeDB(
        get_map={(MCPConnection, 5): builtin},
        execute_queue=[_ExecResult(single=_project()), _ExecResult(single=_project())],
    )
    _override(db)
    try:
        client = TestClient(app)
        patch_response = client.patch(f"{URL}/5", json={"name": "Renamed"})
        delete_response = client.delete(f"{URL}/5")
    finally:
        _clear()
    assert patch_response.status_code == 422
    assert delete_response.status_code == 422
    assert db.deleted == []


def test_update_resets_health_status():
    connection = _connection(id=10, status="connected", tool_count=5)
    db = _FakeDB(
        get_map={(MCPConnection, 10): connection},
        execute_queue=[_ExecResult(single=_project())],
    )
    _override(db)
    try:
        response = TestClient(app).patch(f"{URL}/10", json={"target": "Order API UAT"})
    finally:
        _clear()
    assert response.status_code == 200
    assert connection.status == "not_configured"
    assert connection.tool_count is None


def test_list_seeds_builtin_row():
    db = _FakeDB(execute_queue=[
        _ExecResult(single=_project()),   # require_project_access
        _ExecResult(many=[]),             # ensure_builtin: no existing builtin
        _ExecResult(many=[]),             # list_connections (fake returns empty)
    ])
    _override(db)
    try:
        response = TestClient(app).get(URL, params={"project_id": 1})
    finally:
        _clear()
    assert response.status_code == 200
    seeded = [o for o in db.added if isinstance(o, MCPConnection)]
    assert len(seeded) == 1
    assert seeded[0].is_builtin is True
    assert seeded[0].name == "Playwright Browser MCP"
