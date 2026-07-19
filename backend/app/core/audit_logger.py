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


def _emit(_event: str, **fields: Any) -> None:
    """Write one structured audit event as a JSON log line at INFO level."""
    record = {
        "ts": _now(),
        "event": _event,
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


# ── Resource Intelligence & Utilization Hub events ───────────────────────────

def ldap_sync(by_user_id: int, synced_count: int) -> None:
    _emit("ldap.sync", by_user_id=by_user_id, synced_count=synced_count)


def resource_mapping_updated(by_user_id: int, mapping_id: int, status: str) -> None:
    _emit("resource.mapping_updated", by_user_id=by_user_id, mapping_id=mapping_id, status=status)


def estimate_override(by_user_id: int, estimate_id: int, approved_hours: float) -> None:
    _emit("estimate.override", by_user_id=by_user_id, estimate_id=estimate_id, approved_hours=approved_hours)


def privacy_consent_changed(ldap_username: str, consent_status: str) -> None:
    _emit("privacy.consent_changed", ldap_username=ldap_username, consent_status=consent_status)


def report_exported(by_user_id: int, report_name: str, format_type: str) -> None:
    _emit("report.exported", by_user_id=by_user_id, report_name=report_name, format_type=format_type)


# ── Test Execution events ─────────────────────────────────────────────────────

def execution_run_started(
    by_user_id: int,
    run_id: int,
    project_id: int,
    execution_type: str,
    environment: str | None = None,
    test_case_count: int = 0,
) -> None:
    _emit(
        "execution.run_started",
        by_user_id=by_user_id,
        run_id=run_id,
        project_id=project_id,
        execution_type=execution_type,
        environment=environment,
        test_case_count=test_case_count,
    )


def execution_run_state_changed(
    by_user_id: int | None,
    run_id: int,
    previous_status: str,
    new_status: str,
    reason: str | None = None,
) -> None:
    _emit(
        "execution.run_state_changed",
        by_user_id=by_user_id,
        run_id=run_id,
        previous_status=previous_status,
        new_status=new_status,
        reason=reason,
    )


def execution_run_auto_completed(
    run_id: int,
    project_id: int,
    confidence_score: float | None,
    rule: str,
) -> None:
    _emit(
        "execution.ai_run_auto_completed",
        run_id=run_id,
        project_id=project_id,
        confidence_score=confidence_score,
        rule=rule,
    )


def execution_run_review_required(
    run_id: int,
    project_id: int,
    confidence_score: float | None,
    reason: str,
) -> None:
    _emit(
        "execution.ai_run_review_required",
        run_id=run_id,
        project_id=project_id,
        confidence_score=confidence_score,
        reason=reason,
    )


def test_case_bulk_updated(
    by_user_id: int,
    project_id: int,
    requested: int,
    updated: int,
    skipped: int,
    conflicts: int,
    reason: str,
    patch_fields: list[str],
) -> None:
    """Summary event for a bulk-update call. One per call.

    Per-row field changes are still written to the `test_case_history` table by
    the existing per-row update path, so the row-level diff is preserved there.
    """
    _emit(
        "test_case.bulk_updated",
        by_user_id=by_user_id,
        project_id=project_id,
        requested=requested,
        updated=updated,
        skipped=skipped,
        conflicts=conflicts,
        reason=reason,
        patch_fields=patch_fields,
    )


def execution_run_reviewed(
    by_user_id: int,
    run_id: int,
    decision: str,
    override_status: str | None = None,
    reason: str | None = None,
) -> None:
    _emit(
        "execution.ai_run_reviewed",
        by_user_id=by_user_id,
        run_id=run_id,
        decision=decision,
        override_status=override_status,
        reason=reason,
    )

