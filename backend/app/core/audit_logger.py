"""
Security audit logger (SEC-025).

Provides structured logging for all security-relevant events:
  - Authentication (login, logout, registration, password change)
  - Authorization failures
  - Token lifecycle (issue, revocation)
  - File uploads
  - LLM and Jira configuration changes
  - Permission and role changes

Events are written to the application logger under the "security.audit" namespace
so they can be routed to a dedicated log sink (ELK, CloudWatch, Splunk) via
logging configuration without changing code.

Usage:
    from app.core.audit_logger import audit

    await audit.login_success(user_id=user.id, email=user.email, ip=client_ip)
    await audit.login_failure(email=data.email, ip=client_ip, reason="bad_password")
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

_audit_logger = logging.getLogger("security.audit")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit(event_type: str, **fields: Any) -> None:
    """Write one structured audit event as a JSON log line at INFO level."""
    record = {
        "ts": _now(),
        "event": event_type,
        **{k: v for k, v in fields.items() if v is not None},
    }
    _audit_logger.info(json.dumps(record, default=str))


# ── Authentication events ─────────────────────────────────────────────────────

def login_success(user_id: int, email: str, ip: str | None = None) -> None:
    _emit("auth.login_success", user_id=user_id, email=email, ip=ip)


def login_failure(email: str, ip: str | None = None, reason: str | None = None) -> None:
    _emit("auth.login_failure", email=email, ip=ip, reason=reason)


def logout(user_id: int, email: str, jti: str | None = None, ip: str | None = None) -> None:
    _emit("auth.logout", user_id=user_id, email=email, jti=jti, ip=ip)


def token_issued(user_id: int, jti: str | None = None, expires_in_seconds: int | None = None) -> None:
    _emit("auth.token_issued", user_id=user_id, jti=jti, expires_in_seconds=expires_in_seconds)


def token_revoked(user_id: int | None = None, jti: str | None = None, reason: str | None = None) -> None:
    _emit("auth.token_revoked", user_id=user_id, jti=jti, reason=reason)


def token_rejected(jti: str | None = None, reason: str | None = None, ip: str | None = None) -> None:
    _emit("auth.token_rejected", jti=jti, reason=reason, ip=ip)


# ── Registration / account events ─────────────────────────────────────────────

def registration(email: str, ip: str | None = None, success: bool = True, reason: str | None = None) -> None:
    _emit("auth.registration", email=email, ip=ip, success=success, reason=reason)


def password_changed(user_id: int, ip: str | None = None) -> None:
    _emit("auth.password_changed", user_id=user_id, ip=ip)


def account_deactivated(target_user_id: int, by_user_id: int | None = None) -> None:
    _emit("auth.account_deactivated", target_user_id=target_user_id, by_user_id=by_user_id)


# ── Authorization events ──────────────────────────────────────────────────────

def access_denied(
    user_id: int | None,
    resource: str,
    action: str,
    ip: str | None = None,
    reason: str | None = None,
) -> None:
    _emit("authz.access_denied", user_id=user_id, resource=resource, action=action, ip=ip, reason=reason)


def permission_changed(
    target_user_id: int,
    project_id: int | None,
    old_role: str | None,
    new_role: str | None,
    by_user_id: int | None = None,
) -> None:
    _emit(
        "authz.permission_changed",
        target_user_id=target_user_id,
        project_id=project_id,
        old_role=old_role,
        new_role=new_role,
        by_user_id=by_user_id,
    )


# ── File upload events ────────────────────────────────────────────────────────

def file_uploaded(
    user_id: int,
    project_id: int,
    filename: str,
    file_type: str,
    size_bytes: int,
    ip: str | None = None,
) -> None:
    _emit(
        "file.uploaded",
        user_id=user_id,
        project_id=project_id,
        filename=filename,
        file_type=file_type,
        size_bytes=size_bytes,
        ip=ip,
    )


def file_upload_rejected(
    user_id: int | None,
    filename: str,
    reason: str,
    ip: str | None = None,
) -> None:
    _emit("file.upload_rejected", user_id=user_id, filename=filename, reason=reason, ip=ip)


# ── LLM configuration events ──────────────────────────────────────────────────

def llm_config_changed(
    user_id: int,
    project_id: int,
    old_provider: str | None,
    new_provider: str | None,
    old_model: str | None = None,
    new_model: str | None = None,
) -> None:
    _emit(
        "config.llm_changed",
        user_id=user_id,
        project_id=project_id,
        old_provider=old_provider,
        new_provider=new_provider,
        old_model=old_model,
        new_model=new_model,
    )


# ── Jira integration events ───────────────────────────────────────────────────

def jira_connection_created(user_id: int, project_id: int, jira_base_url: str) -> None:
    _emit("jira.connection_created", user_id=user_id, project_id=project_id, jira_base_url=jira_base_url)


def jira_connection_deleted(user_id: int, project_id: int, connection_id: int) -> None:
    _emit("jira.connection_deleted", user_id=user_id, project_id=project_id, connection_id=connection_id)


def jira_import(user_id: int, project_id: int, issue_count: int) -> None:
    _emit("jira.import", user_id=user_id, project_id=project_id, issue_count=issue_count)


def jira_webhook_received(project_id: int | None, event_type: str | None, verified: bool) -> None:
    _emit("jira.webhook_received", project_id=project_id, event_type=event_type, verified=verified)


def jira_webhook_rejected(reason: str, ip: str | None = None) -> None:
    _emit("jira.webhook_rejected", reason=reason, ip=ip)


# ── Prompt injection detection ────────────────────────────────────────────────

def prompt_injection_detected(
    user_id: int | None,
    project_id: int | None,
    source: str,
    pattern_matched: str | None = None,
) -> None:
    _emit(
        "security.prompt_injection_detected",
        user_id=user_id,
        project_id=project_id,
        source=source,
        pattern_matched=pattern_matched,
    )


# ── Data retention events ─────────────────────────────────────────────────────

def retention_purge(entity_type: str, count: int, cutoff: str) -> None:
    _emit("retention.purge", entity_type=entity_type, count=count, cutoff=cutoff)
