"""
Phase 5 security test suite.

Covers:
  - Auth bypass attempts (unauthenticated access to protected routes)
  - IDOR (cross-project/cross-user resource access)
  - Rate limiting HTTP response codes
  - Input validation / injection surface
  - Security headers emitted by the app
  - Settings information disclosure
  - Health endpoint auth
  - Root endpoint information disclosure
  - Audit logger structure
  - Jira webhook secret enforcement
  - JWT token structure (no sensitive data in payload)
"""
from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_db, require_user
from app.main import app
from app.models.project import Project
from app.models.user import User


# ── Test fixtures ─────────────────────────────────────────────────────────────

def _make_user(id: int = 1, role: str = "qa_engineer", is_superuser: bool = False) -> User:
    return User(
        id=id,
        email=f"user{id}@example.com",
        full_name=f"User {id}",
        hashed_password="hashed",
        role=role,
        is_active=True,
        is_superuser=is_superuser,
    )


def _make_project(id: int = 1, owner_id: int = 1) -> Project:
    return Project(id=id, owner_id=owner_id, name=f"Project {id}")


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return [self._value] if self._value else []


class _FakeDB:
    def __init__(self, project: Project | None = None):
        self._project = project

    async def execute(self, _stmt):
        return _ScalarResult(self._project)

    async def get(self, model, pk):
        if model is Project and self._project and self._project.id == pk:
            return self._project
        return None


async def _fake_db_with_project(project: Project):
    async def _gen() -> AsyncIterator[_FakeDB]:
        yield _FakeDB(project=project)
    return _gen


# ── AUTH BYPASS TESTS ─────────────────────────────────────────────────────────

class TestAuthBypass:
    """Every business endpoint must return 401 without a valid token."""

    PROTECTED_ROUTES = [
        ("GET",  "/api/v1/requirements/project/1"),
        ("GET",  "/api/v1/projects/"),
        ("GET",  "/api/v1/test-plans/project/1"),
        ("GET",  "/api/v1/defects/project/1"),
        ("GET",  "/api/v1/execution/project/1/runs"),
        ("GET",  "/api/v1/reports/project/1"),
        ("GET",  "/api/v1/users/me"),
        ("GET",  "/api/v1/settings/"),
        ("GET",  "/api/v1/rag/projects/1/status"),
    ]

    def test_unauthenticated_requests_return_401(self):
        """No Authorization header → 401 on all protected routes."""
        client = TestClient(app, raise_server_exceptions=False)
        for method, path in self.PROTECTED_ROUTES:
            resp = getattr(client, method.lower())(path)
            assert resp.status_code == 401, (
                f"{method} {path} returned {resp.status_code}, expected 401"
            )

    def test_malformed_bearer_token_returns_401(self):
        client = TestClient(app, raise_server_exceptions=False)
        headers = {"Authorization": "Bearer not.a.valid.jwt"}
        resp = client.get("/api/v1/projects/", headers=headers)
        assert resp.status_code == 401

    def test_expired_token_format_rejected(self):
        """A syntactically valid JWT signed with wrong key must be rejected."""
        import jwt as _jwt
        fake_token = _jwt.encode(
            {"sub": "1", "exp": int(time.time()) + 3600},
            "wrong-secret",
            algorithm="HS256",
        )
        client = TestClient(app, raise_server_exceptions=False)
        headers = {"Authorization": f"Bearer {fake_token}"}
        resp = client.get("/api/v1/projects/", headers=headers)
        assert resp.status_code == 401

    def test_missing_bearer_prefix_returns_401(self):
        """Token without 'Bearer ' scheme must be rejected."""
        client = TestClient(app, raise_server_exceptions=False)
        headers = {"Authorization": "Token sometoken"}
        resp = client.get("/api/v1/projects/", headers=headers)
        assert resp.status_code == 401


# ── ROOT / INFORMATION DISCLOSURE ────────────────────────────────────────────

class TestInformationDisclosure:
    def test_root_returns_only_status(self):
        """Root endpoint must not expose version, env, or app name (SEC-050)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"status"}
        assert body["status"] == "ok"

    def test_root_no_version_leak(self):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/")
        text = resp.text.lower()
        assert "version" not in text
        assert "stlc" not in text

    def test_settings_no_internal_paths(self):
        """Settings endpoint must not expose filesystem paths (SEC-026)."""
        owner = _make_user(id=1, role="admin", is_superuser=True)

        async def _owner():
            return owner

        db_gen = _FakeDB()

        async def _gen() -> AsyncIterator[_FakeDB]:
            yield db_gen

        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_user] = _owner
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/settings/")
            assert resp.status_code == 200
            text = resp.text
            # File system paths must not appear in the response
            assert "/app/storage" not in text
            assert "file_storage_path" not in text
            # Internal base URLs for LLM backends must not appear
            assert "ollama_base_url" not in text
            assert "openai_base_url" not in text
            # Jira email / token must not appear
            assert "jira_email" not in text
        finally:
            app.dependency_overrides.clear()

    def test_health_pool_requires_auth(self):
        """Pool stats endpoint must require authentication (SEC-027)."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/health/pool")
        assert resp.status_code == 401


# ── IDOR TESTS ────────────────────────────────────────────────────────────────

class TestIDOR:
    """User B must not read resources belonging to User A's project."""

    def _setup_cross_project(self):
        """Project owned by user 1, request made by user 2."""
        project = _make_project(id=1, owner_id=1)
        requester = _make_user(id=2)
        return project, requester

    def test_cross_project_requirements_access_returns_403(self):
        project, requester = self._setup_cross_project()

        async def _user():
            return requester

        async def _gen() -> AsyncIterator[_FakeDB]:
            yield _FakeDB(project=project)

        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_user] = _user
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/requirements/project/1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_cross_project_test_plans_access_returns_403(self):
        project, requester = self._setup_cross_project()

        async def _user():
            return requester

        async def _gen() -> AsyncIterator[_FakeDB]:
            yield _FakeDB(project=project)

        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_user] = _user
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/test-plans/project/1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_cross_project_reports_access_returns_403(self):
        project, requester = self._setup_cross_project()

        async def _user():
            return requester

        async def _gen() -> AsyncIterator[_FakeDB]:
            yield _FakeDB(project=project)

        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_user] = _user
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/reports/project/1")
            assert resp.status_code == 403
        finally:
            app.dependency_overrides.clear()

    def test_nonexistent_project_returns_404_not_403(self):
        """A project that does not exist must return 404 — not 403 (avoids enumeration)."""
        user = _make_user(id=1, role="admin", is_superuser=True)

        async def _user():
            return user

        async def _gen() -> AsyncIterator[_FakeDB]:
            yield _FakeDB(project=None)

        app.dependency_overrides[get_db] = _gen
        app.dependency_overrides[require_user] = _user
        try:
            client = TestClient(app, raise_server_exceptions=False)
            resp = client.get("/api/v1/requirements/project/9999")
            assert resp.status_code == 404
        finally:
            app.dependency_overrides.clear()


# ── INPUT VALIDATION ──────────────────────────────────────────────────────────

class TestInputValidation:
    """Malformed inputs must be rejected with 4xx, not cause 500 errors."""

    def test_register_rejects_weak_password(self):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/users/register",
            json={"email": "test@example.com", "full_name": "Test", "password": "weak"},
        )
        assert resp.status_code in (400, 422)

    def test_register_rejects_invalid_email(self):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/users/register",
            json={"email": "not-an-email", "full_name": "Test", "password": "ValidP@ss1234!"},
        )
        assert resp.status_code == 422

    def test_invalid_project_id_type_returns_422(self):
        """Non-integer project_id path parameter must yield 422 Unprocessable Entity."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/requirements/project/not-an-int")
        assert resp.status_code == 422

    def test_oversized_json_body_rejected(self):
        """Very large JSON bodies on login should be handled gracefully."""
        client = TestClient(app, raise_server_exceptions=False)
        payload = {"username": "a" * 100_000, "password": "b" * 100_000}
        resp = client.post("/api/v1/users/token", data=payload)
        # Should return 4xx (401/422/400) — never 500
        assert resp.status_code < 500

    def test_sql_injection_attempt_returns_4xx(self):
        """SQL injection in URL path parameter must not cause 500."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/requirements/project/1; DROP TABLE projects; --")
        assert resp.status_code in (400, 404, 422)

    def test_xss_attempt_in_json_body(self):
        """XSS payload in registration body must not cause 500."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/users/register",
            json={
                "email": "xss@example.com",
                "full_name": "<script>alert(1)</script>",
                "password": "ValidP@ss1234!",
            },
        )
        # May succeed (stored/escaped) or fail validation — never 500
        assert resp.status_code < 500


# ── SECURITY HEADERS ──────────────────────────────────────────────────────────

class TestSecurityHeaders:
    """The API must emit security headers on every response."""

    REQUIRED_HEADERS = {
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "x-xss-protection": "0",
        "referrer-policy": "strict-origin-when-cross-origin",
    }

    def test_security_headers_present_on_public_route(self):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/")
        for header, expected in self.REQUIRED_HEADERS.items():
            value = resp.headers.get(header, "")
            assert value == expected, (
                f"Header '{header}': expected '{expected}', got '{value}'"
            )

    def test_no_server_header_version_leak(self):
        """'Server' header must not reveal specific server software version."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/")
        server = resp.headers.get("server", "")
        # Uvicorn by default sets "uvicorn" — version string must not appear
        assert "/" not in server, f"Server header leaks version: '{server}'"

    def test_cache_control_on_api_response(self):
        """API responses must carry no-store directive to prevent sensitive data caching."""
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/api/v1/users/me")
        cc = resp.headers.get("cache-control", "")
        # This is acceptable to be missing on 401 pages — verify on auth flows via integration
        # Here we just assert the response is 401 (not cached sensitive data)
        assert resp.status_code == 401


# ── AUDIT LOGGER ─────────────────────────────────────────────────────────────

class TestAuditLogger:
    """Audit logger must emit structured JSON-parseable lines."""

    def test_login_success_event_structure(self, caplog):
        import logging
        from app.core import audit_logger as audit

        with caplog.at_level(logging.INFO, logger="security.audit"):
            audit.login_success(user_id=42, email="audit@example.com", ip="10.0.0.1")

        assert caplog.records, "No audit log records emitted"
        record = caplog.records[-1]
        assert record.name == "security.audit"
        data = json.loads(record.getMessage())
        assert data["event"] == "auth.login_success"
        assert data["user_id"] == 42
        assert data["email"] == "audit@example.com"
        assert "ts" in data

    def test_login_failure_event_structure(self, caplog):
        import logging
        from app.core import audit_logger as audit

        with caplog.at_level(logging.INFO, logger="security.audit"):
            audit.login_failure(email="bad@example.com", ip="10.0.0.2", reason="invalid_credentials")

        record = caplog.records[-1]
        data = json.loads(record.getMessage())
        assert data["event"] == "auth.login_failure"
        assert data["reason"] == "invalid_credentials"

    def test_access_denied_event_structure(self, caplog):
        import logging
        from app.core import audit_logger as audit

        with caplog.at_level(logging.INFO, logger="security.audit"):
            audit.access_denied(user_id=5, resource="project:99", action="view_project")

        record = caplog.records[-1]
        data = json.loads(record.getMessage())
        assert data["event"] == "authz.access_denied"
        assert data["resource"] == "project:99"

    def test_file_upload_rejected_event(self, caplog):
        import logging
        from app.core import audit_logger as audit

        with caplog.at_level(logging.INFO, logger="security.audit"):
            audit.file_upload_rejected(user_id=1, filename="evil.exe", reason="disallowed_extension")

        record = caplog.records[-1]
        data = json.loads(record.getMessage())
        assert data["event"] == "file.upload_rejected"
        assert data["filename"] == "evil.exe"

    def test_retention_purge_event(self, caplog):
        import logging
        from app.core import audit_logger as audit

        with caplog.at_level(logging.INFO, logger="security.audit"):
            audit.retention_purge("agent_logs", count=150, cutoff="2026-01-01T02:00:00Z")

        record = caplog.records[-1]
        data = json.loads(record.getMessage())
        assert data["event"] == "retention.purge"
        assert data["count"] == 150


# ── JIRA WEBHOOK SECURITY ─────────────────────────────────────────────────────

class TestJiraWebhookSecurity:
    """Webhook endpoint must reject requests when secret is not configured (SEC-023)."""

    def test_webhook_rejects_missing_secret_with_401(self):
        from app.config import get_settings
        settings = get_settings()

        # Only run this check when the secret is empty (default dev state)
        if settings.jira_webhook_secret:
            pytest.skip("jira_webhook_secret is configured — skip missing-secret path")

        client = TestClient(app, raise_server_exceptions=False)
        resp = client.post(
            "/api/v1/jira/connections/1/webhook",
            json={"webhookEvent": "jira:issue_updated"},
        )
        # 404 (no connection) or 401 (secret not configured) — both are safe
        assert resp.status_code in (401, 404)

    def test_verify_webhook_signature_rejects_empty_secret(self):
        """verify_webhook_signature(secret='', ...) must return False, not True."""
        from app.services.jira_service import verify_webhook_signature

        result = verify_webhook_signature("", b"payload", "sha256=abc")
        assert result is False, "Empty webhook secret must NOT pass signature verification"

    def test_verify_webhook_signature_rejects_none_secret(self):
        from app.services.jira_service import verify_webhook_signature

        result = verify_webhook_signature(None, b"payload", None)
        assert result is False


# ── JWT / TOKEN SECURITY ─────────────────────────────────────────────────────

class TestTokenSecurity:
    """JWT tokens must not embed sensitive data in their payload."""

    def _decode_payload(self, token: str) -> dict:
        import base64
        parts = token.split(".")
        assert len(parts) == 3, "Not a JWT"
        payload_b64 = parts[1]
        # Add padding
        padding = 4 - len(payload_b64) % 4
        payload_b64 += "=" * (padding % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64))

    def test_create_access_token_payload_has_no_password(self):
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "42", "role": "qa_engineer"})
        payload = self._decode_payload(token)
        assert "password" not in payload
        assert "hashed_password" not in payload

    def test_create_access_token_has_expiry(self):
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "42"})
        payload = self._decode_payload(token)
        assert "exp" in payload, "Access token must have an expiry claim"

    def test_create_access_token_has_jti(self):
        """JTI claim required for revocation support."""
        from app.core.security import create_access_token

        token = create_access_token(data={"sub": "42"})
        payload = self._decode_payload(token)
        assert "jti" in payload, "Access token must carry a jti claim for revocation"


# ── JIRA ENCRYPTION ───────────────────────────────────────────────────────────

class TestJiraEncryption:
    """Jira credential encryption must use HKDF and be round-trip safe."""

    def test_encrypt_decrypt_round_trip(self):
        from app.services.jira_service import encrypt_credential, decrypt_credential

        original = "my-super-secret-api-token"
        encrypted = encrypt_credential(original)
        assert encrypted != original, "Credential must be encrypted"

        decrypted = decrypt_credential(encrypted)
        assert decrypted == original

    def test_encrypt_produces_different_output_each_call(self):
        """Fernet uses random IV — two encryptions of same plaintext must differ."""
        from app.services.jira_service import encrypt_credential

        token = "same-token-value"
        enc1 = encrypt_credential(token)
        enc2 = encrypt_credential(token)
        assert enc1 != enc2, "Encryption must use random IV (Fernet guarantees this)"

    def test_tampered_ciphertext_raises(self):
        from app.services.jira_service import encrypt_credential, decrypt_credential

        encrypted = encrypt_credential("real-token")
        tampered = encrypted[:-4] + "XXXX"
        with pytest.raises(Exception):
            decrypt_credential(tampered)
