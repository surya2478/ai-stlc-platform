"""Jira integration service."""
from __future__ import annotations

import base64
import hmac
import hashlib
import html
import logging
import os
import re
from dataclasses import dataclass
from math import ceil
from typing import Any

import httpx
from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives.hashes import SHA256
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.jira_connection import JiraConnection
from app.models.jira_sync import ConflictRecord, JiraSyncHistory, WebhookEvent
from app.models.requirement import Requirement
from app.schemas.jira import (
    JiraConnectionCreate,
    JiraConnectionTestOut,
    JiraConnectionUpdate,
    JiraFetchIssuesRequest,
    JiraImportRequirementsRequest,
    JiraImportRequirementsOut,
    JiraIssueOut,
    JiraIssuePageOut,
    JiraSyncTriggerRequest,
)

settings = get_settings()
logger = logging.getLogger(__name__)

# Salt for HKDF — fixed per-deployment so encrypted values remain decryptable.
# This is not a secret; its purpose is domain separation, not password hardening.
_HKDF_SALT = b"stlc-platform-jira-credential-v2"
_HKDF_INFO = b"jira-api-token"


def _derive_key_hkdf(secret: str) -> bytes:
    """
    SEC-032: Derive a 32-byte key using HKDF with SHA-256.
    Stronger than a raw SHA-256 digest — uses key-stretching context separation.
    """
    hkdf = HKDF(
        algorithm=SHA256(),
        length=32,
        salt=_HKDF_SALT,
        info=_HKDF_INFO,
    )
    return hkdf.derive(secret.encode("utf-8"))


def _derive_key_sha256_legacy(secret: str) -> bytes:
    """Legacy key derivation — used only for backward-compatible decryption."""
    return hashlib.sha256(secret.encode("utf-8")).digest()


def _fernet_hkdf() -> Fernet:
    key = _derive_key_hkdf(settings.app_secret_key)
    return Fernet(base64.urlsafe_b64encode(key))


def _fernet_legacy() -> Fernet:
    key = _derive_key_sha256_legacy(settings.app_secret_key)
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_credential(value: str) -> str:
    """Encrypt a credential using HKDF-derived Fernet key (SEC-032)."""
    return _fernet_hkdf().encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_credential(value: str) -> str:
    """
    Decrypt a credential. Tries the new HKDF key first; falls back to the
    legacy SHA-256 key for tokens encrypted before the HKDF migration.
    """
    try:
        return _fernet_hkdf().decrypt(value.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        pass
    # Backward-compat fallback for tokens stored before migration
    try:
        plaintext = _fernet_legacy().decrypt(value.encode("utf-8")).decode("utf-8")
        logger.info("Decrypted Jira credential with legacy key — will re-encrypt on next save")
        return plaintext
    except InvalidToken as exc:
        raise HTTPException(status_code=500, detail="Stored Jira credential could not be decrypted") from exc


def _quote_jql_value(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _truncate(value: str | None, max_length: int, fallback: str) -> str:
    value = (value or fallback).strip() or fallback
    return value[:max_length]


def parse_jira_datetime(value: str | None):
    if not value:
        return None
    from datetime import datetime

    normalized = value.replace("Z", "+00:00")
    if len(normalized) >= 5 and normalized[-5] in {"+", "-"} and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


ORDER_BY_RE = re.compile(r"\s+order\s+by\s+", re.IGNORECASE)


def _split_jql_order(jql: str) -> tuple[str, str | None]:
    match = ORDER_BY_RE.search(jql)
    if not match:
        return jql.strip(), None
    return jql[: match.start()].strip(), jql[match.start() :].strip()


def build_jql(project_key: str, filters: JiraFetchIssuesRequest | JiraImportRequirementsRequest | JiraSyncTriggerRequest) -> str:
    clauses = [f"project = {_quote_jql_value(project_key)}"]
    order_by = "ORDER BY updated DESC"
    if filters.issue_types:
        values = ", ".join(_quote_jql_value(v) for v in filters.issue_types)
        clauses.append(f"issuetype in ({values})")
    if filters.statuses:
        values = ", ".join(_quote_jql_value(v) for v in filters.statuses)
        clauses.append(f"status in ({values})")
    if filters.priorities:
        values = ", ".join(_quote_jql_value(v) for v in filters.priorities)
        clauses.append(f"priority in ({values})")
    if filters.labels:
        values = ", ".join(_quote_jql_value(v) for v in filters.labels)
        clauses.append(f"labels in ({values})")
    if filters.assignee:
        clauses.append(f"assignee = {_quote_jql_value(filters.assignee)}")
    if filters.text:
        clauses.append(f"text ~ {_quote_jql_value(filters.text)}")
    if filters.updated_since:
        clauses.append(f"updated >= {_quote_jql_value(filters.updated_since)}")
    if filters.jql:
        custom_jql, custom_order = _split_jql_order(filters.jql)
        if custom_jql:
            clauses.append(f"({custom_jql})")
        if custom_order:
            order_by = custom_order
    return " AND ".join(clauses) + f" {order_by}"


def _description_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        texts: list[str] = []

        def collect(node: Any) -> None:
            if isinstance(node, dict):
                if node.get("type") == "text" and isinstance(node.get("text"), str):
                    texts.append(node["text"])
                for child in node.get("content", []) or []:
                    collect(child)
            elif isinstance(node, list):
                for child in node:
                    collect(child)

        collect(value)
        return "\n".join(texts) if texts else None
    return str(value)


def normalize_issue(issue: dict[str, Any]) -> JiraIssueOut:
    fields = issue.get("fields") or {}
    key = _truncate(str(issue.get("key") or ""), 100, "")
    if not key:
        raise HTTPException(status_code=502, detail="Jira returned an issue without a key")
    return JiraIssueOut(
        key=key,
        summary=_truncate(fields.get("summary"), 500, key),
        description=_description_to_text(fields.get("description")),
        issue_type=_truncate((fields.get("issuetype") or {}).get("name"), 100, "") or None,
        status=(fields.get("status") or {}).get("name"),
        priority=_truncate((fields.get("priority") or {}).get("name"), 50, "") or None,
        labels=list(fields.get("labels") or []),
        updated=fields.get("updated"),
        raw=issue,
    )


def webhook_event_key(payload: dict[str, Any]) -> str:
    explicit = payload.get("webhookEventId") or payload.get("event_key")
    issue = payload.get("issue") or {}
    issue_key = issue.get("key") or payload.get("issue_key") or "unknown"
    event_type = payload.get("webhookEvent") or payload.get("event_type") or payload.get("issue_event_type_name")
    timestamp = payload.get("timestamp") or payload.get("updated") or ""
    raw = str(explicit or f"{event_type}:{issue_key}:{timestamp}")
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def verify_webhook_signature(secret: str, body: bytes, signature: str | None) -> bool:
    # SEC-023: Reject all webhooks when no secret is configured — never accept blindly.
    if not secret:
        return False
    if not signature:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    supplied = signature.removeprefix("sha256=").strip()
    return hmac.compare_digest(expected, supplied)


def _search_total_lower_bound(data: dict[str, Any], page: int, page_size: int, item_count: int) -> int:
    if data.get("total") is not None:
        try:
            return int(data.get("total") or 0)
        except (TypeError, ValueError):
            pass
    seen_through_page = ((page - 1) * page_size) + item_count
    if data.get("isLast", True):
        return seen_through_page
    return seen_through_page + 1


@dataclass
class JiraService:
    db: AsyncSession
    http_client: httpx.AsyncClient | None = None

    async def create_connection(self, data: JiraConnectionCreate, user_id: int) -> JiraConnection:
        connection = JiraConnection(
            project_id=data.project_id,
            created_by=user_id,
            jira_base_url=data.jira_base_url,
            jira_email=data.jira_email,
            jira_api_token_encrypted=encrypt_credential(data.jira_api_token),
            jira_project_key=data.jira_project_key,
            is_active=data.is_active,
            status="connected",
            metadata_=data.metadata_,
        )
        self.db.add(connection)
        await self.db.flush()
        await self.db.refresh(connection)
        return connection

    async def list_connections(self, project_id: int) -> list[JiraConnection]:
        result = await self.db.execute(
            select(JiraConnection)
            .where(JiraConnection.project_id == project_id)
            .order_by(JiraConnection.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_connection(self, connection_id: int) -> JiraConnection | None:
        result = await self.db.execute(select(JiraConnection).where(JiraConnection.id == connection_id))
        return result.scalar_one_or_none()

    async def update_connection(self, connection: JiraConnection, data: JiraConnectionUpdate) -> JiraConnection:
        updates = data.model_dump(exclude_unset=True)
        token = updates.pop("jira_api_token", None)
        if token is not None:
            connection.jira_api_token_encrypted = encrypt_credential(token)
        for key, value in updates.items():
            setattr(connection, key, value)
        await self.db.flush()
        await self.db.refresh(connection)
        return connection

    async def delete_connection(self, connection: JiraConnection) -> None:
        await self.db.delete(connection)
        await self.db.flush()

    def decrypt_token(self, connection: JiraConnection) -> str:
        return decrypt_credential(connection.jira_api_token_encrypted)

    def ensure_active(self, connection: JiraConnection) -> None:
        if not connection.is_active:
            raise HTTPException(status_code=409, detail="Jira connection is inactive")

    async def test_connection(self, connection: JiraConnection) -> JiraConnectionTestOut:
        self.ensure_active(connection)
        token = self.decrypt_token(connection)
        try:
            data = await self._request(
                connection,
                "GET",
                "/rest/api/3/myself",
                token=token,
            )
        except HTTPException as exc:
            connection.status = "error"
            detail = str(exc.detail)
            if "HTTP 401" in detail or "Unauthorized" in detail:
                detail = (
                    "Jira authentication failed. Verify the Jira email and API token, "
                    "then save the connection again with the new token."
                )
            metadata = dict(connection.metadata_ or {})
            metadata["last_test_error"] = detail
            connection.metadata_ = metadata
            await self.db.flush()
            return JiraConnectionTestOut(success=False, message=detail)
        connection.status = "connected"
        metadata = dict(connection.metadata_ or {})
        metadata.pop("last_test_error", None)
        connection.metadata_ = metadata
        await self.db.flush()
        return JiraConnectionTestOut(
            success=True,
            message="Jira connection successful",
            account_id=data.get("accountId"),
            display_name=data.get("displayName"),
        )

    async def fetch_issues(self, connection: JiraConnection, filters: JiraFetchIssuesRequest) -> JiraIssuePageOut:
        self.ensure_active(connection)
        jql = build_jql(connection.jira_project_key, filters)
        try:
            data = await self._search_page_for_number(
                connection,
                jql,
                page=filters.page,
                page_size=filters.page_size,
            )
        except HTTPException:
            connection.status = "error"
            await self.db.flush()
            raise
        items = [normalize_issue(issue) for issue in data.get("issues", [])]
        total = _search_total_lower_bound(data, filters.page, filters.page_size, len(items))
        pages = ceil(total / filters.page_size) if total else (filters.page + (0 if data.get("isLast", True) else 1))
        return JiraIssuePageOut(
            items=items,
            total=total,
            page=filters.page,
            page_size=filters.page_size,
            pages=pages,
            jql=jql,
        )

    async def import_requirements(
        self,
        connection: JiraConnection,
        body: JiraImportRequirementsRequest,
        user_id: int,
    ) -> JiraImportRequirementsOut:
        self.ensure_active(connection)
        jql = build_jql(connection.jira_project_key, body)
        imported = created = updated = 0
        requirement_ids: list[int] = []
        seen_issue_keys: set[str] = set()

        try:
            next_page_token: str | None = None
            while imported < body.max_issues:
                batch_size = min(body.batch_size, body.max_issues - imported)
                data = await self._search(connection, jql, next_page_token=next_page_token, max_results=batch_size)
                issues = data.get("issues", [])
                if not issues:
                    break

                for raw_issue in issues:
                    issue = normalize_issue(raw_issue)
                    if issue.key in seen_issue_keys:
                        continue
                    seen_issue_keys.add(issue.key)
                    was_created, requirement = await self._upsert_requirement_from_issue(
                        connection=connection,
                        issue=issue,
                        user_id=user_id,
                    )
                    created += 1 if was_created else 0
                    updated += 0 if was_created else 1
                    if requirement.id is not None:
                        requirement_ids.append(requirement.id)
                    imported += 1
                    if imported >= body.max_issues:
                        break

                next_page_token = data.get("nextPageToken")
                if data.get("isLast", not next_page_token) or not next_page_token:
                    break
        except HTTPException:
            connection.status = "error"
            await self.db.flush()
            raise

        connection.last_sync_at = datetime_iso()
        connection.status = "connected"
        await self.db.flush()
        return JiraImportRequirementsOut(
            imported=imported,
            created=created,
            updated=updated,
            requirement_ids=requirement_ids,
        )

    async def create_sync_history(
        self,
        *,
        connection: JiraConnection,
        direction: str,
        user_id: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> JiraSyncHistory:
        history = JiraSyncHistory(
            project_id=connection.project_id,
            connection_id=connection.id,
            triggered_by=user_id,
            direction=direction,
            status="queued",
            total_items=0,
            created_count=0,
            updated_count=0,
            conflict_count=0,
            metadata_=metadata,
        )
        self.db.add(history)
        await self.db.flush()
        await self.db.refresh(history)
        return history

    async def sync_inbound(
        self,
        connection: JiraConnection,
        body: JiraSyncTriggerRequest | JiraImportRequirementsRequest | None,
        *,
        user_id: int | None = None,
        sync_history_id: int | None = None,
    ) -> JiraSyncHistory:
        self.ensure_active(connection)
        history = await self._load_or_create_history(
            connection=connection,
            direction="inbound",
            user_id=user_id,
            sync_history_id=sync_history_id,
            metadata=(body.model_dump(mode="json") if body else None),
        )
        history.status = "running"
        history.started_at = now_utc()
        await self.db.flush()

        filters = body or JiraSyncTriggerRequest()
        jql = build_jql(connection.jira_project_key, filters)
        next_page_token: str | None = None
        seen_issue_keys: set[str] = set()

        try:
            while history.total_items < filters.max_issues:
                batch_size = min(filters.batch_size, filters.max_issues - history.total_items)
                data = await self._search(connection, jql, next_page_token=next_page_token, max_results=batch_size)
                issues = data.get("issues", [])
                if not issues:
                    break
                for raw_issue in issues:
                    issue = normalize_issue(raw_issue)
                    if issue.key in seen_issue_keys:
                        continue
                    seen_issue_keys.add(issue.key)
                    created, updated, conflicted = await self._sync_issue_inbound(
                        connection=connection,
                        issue=issue,
                        user_id=user_id or connection.created_by,
                        sync_history_id=history.id,
                    )
                    history.created_count += 1 if created else 0
                    history.updated_count += 1 if updated else 0
                    history.conflict_count += 1 if conflicted else 0
                    history.total_items += 1
                    if history.total_items >= filters.max_issues:
                        break
                next_page_token = data.get("nextPageToken")
                if data.get("isLast", not next_page_token) or not next_page_token:
                    break
            history.status = "completed"
            connection.status = "connected"
            connection.last_sync_at = datetime_iso()
        except Exception as exc:
            history.status = "failed"
            history.error_message = str(exc)
            connection.status = "error"
            raise
        finally:
            history.finished_at = now_utc()
            await self.db.flush()
        return history

    async def sync_outbound(
        self,
        connection: JiraConnection,
        *,
        user_id: int | None = None,
        sync_history_id: int | None = None,
    ) -> JiraSyncHistory:
        self.ensure_active(connection)
        history = await self._load_or_create_history(
            connection=connection,
            direction="outbound",
            user_id=user_id,
            sync_history_id=sync_history_id,
        )
        history.status = "running"
        history.started_at = now_utc()
        await self.db.flush()

        try:
            result = await self.db.execute(
                select(Requirement).where(
                    Requirement.project_id == connection.project_id,
                    Requirement.source == "jira",
                    Requirement.jira_issue_key.is_not(None),
                    Requirement.jira_deleted.is_(False),
                )
            )
            requirements = list(result.scalars().all())
            for requirement in requirements:
                if requirement.jira_last_synced_at and requirement.updated_at <= requirement.jira_last_synced_at:
                    continue
                await self._request(
                    connection,
                    "PUT",
                    f"/rest/api/3/issue/{requirement.jira_issue_key}",
                    token=self.decrypt_token(connection),
                    json={
                        "fields": {
                            "summary": requirement.title,
                            "description": requirement.summary or "",
                        }
                    },
                )
                requirement.jira_last_synced_at = now_utc()
                history.updated_count += 1
                history.total_items += 1
            history.status = "completed"
            connection.status = "connected"
            connection.last_sync_at = datetime_iso()
        except Exception as exc:
            history.status = "failed"
            history.error_message = str(exc)
            connection.status = "error"
            raise
        finally:
            history.finished_at = now_utc()
            await self.db.flush()
        return history

    async def persist_webhook_event(self, connection: JiraConnection, payload: dict[str, Any]) -> tuple[WebhookEvent, bool]:
        event_key = webhook_event_key(payload)
        existing = await self.get_webhook_event_by_key(event_key)
        if existing is not None:
            return existing, False
        event = WebhookEvent(
            project_id=connection.project_id,
            connection_id=connection.id,
            event_key=event_key,
            event_type=payload.get("webhookEvent") or payload.get("event_type") or payload.get("issue_event_type_name"),
            status="queued",
            payload=payload,
        )
        self.db.add(event)
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            existing = await self.get_webhook_event_by_key(event_key)
            if existing is None:
                raise
            return existing, False
        await self.db.refresh(event)
        return event, True

    async def get_webhook_event(self, event_id: int) -> WebhookEvent | None:
        result = await self.db.execute(select(WebhookEvent).where(WebhookEvent.id == event_id))
        return result.scalar_one_or_none()

    async def get_webhook_event_by_key(self, event_key: str) -> WebhookEvent | None:
        result = await self.db.execute(select(WebhookEvent).where(WebhookEvent.event_key == event_key))
        return result.scalar_one_or_none()

    async def process_webhook_event(self, event: WebhookEvent) -> WebhookEvent:
        if event.status == "processed":
            return event
        result = await self.db.execute(select(JiraConnection).where(JiraConnection.id == event.connection_id))
        connection = result.scalar_one_or_none()
        if connection is None:
            raise ValueError(f"JiraConnection {event.connection_id} not found")

        event.status = "processing"
        await self.db.flush()
        try:
            self.ensure_active(connection)
            issue_payload = event.payload.get("issue") or {}
            issue_key = issue_payload.get("key") or event.payload.get("issue_key")
            deleted = (
                event.payload.get("webhookEvent") == "jira:issue_deleted"
                or event.payload.get("issue_event_type_name") == "issue_deleted"
            )
            if issue_key and deleted:
                await self.mark_issue_deleted(connection, issue_key)
            elif issue_payload:
                issue = normalize_issue(issue_payload)
                await self._sync_issue_inbound(
                    connection=connection,
                    issue=issue,
                    user_id=connection.created_by,
                    sync_history_id=None,
                    from_webhook=True,
                )
            event.status = "processed"
            event.processed_at = now_utc()
            event.error_message = None
        except Exception as exc:
            event.status = "failed"
            event.error_message = str(exc)
            raise
        finally:
            await self.db.flush()
        return event

    async def mark_issue_deleted(self, connection: JiraConnection, issue_key: str) -> Requirement | None:
        result = await self.db.execute(
            select(Requirement).where(
                Requirement.project_id == connection.project_id,
                Requirement.requirement_id == issue_key,
            )
        )
        requirement = result.scalar_one_or_none()
        if requirement is None:
            return None
        requirement.jira_deleted = True
        requirement.status = "pending_approval"
        requirement.metadata_ = {
            **(requirement.metadata_ or {}),
            "jira": {**((requirement.metadata_ or {}).get("jira") or {}), "deleted": True},
        }
        requirement.jira_last_synced_at = now_utc()
        await self.db.flush()
        return requirement

    async def _load_or_create_history(
        self,
        *,
        connection: JiraConnection,
        direction: str,
        user_id: int | None,
        sync_history_id: int | None,
        metadata: dict[str, Any] | None = None,
    ) -> JiraSyncHistory:
        if sync_history_id is not None:
            result = await self.db.execute(select(JiraSyncHistory).where(JiraSyncHistory.id == sync_history_id))
            history = result.scalar_one_or_none()
            if history is None:
                raise ValueError(f"JiraSyncHistory {sync_history_id} not found")
            return history
        return await self.create_sync_history(
            connection=connection,
            direction=direction,
            user_id=user_id,
            metadata=metadata,
        )

    async def _sync_issue_inbound(
        self,
        *,
        connection: JiraConnection,
        issue: JiraIssueOut,
        user_id: int,
        sync_history_id: int | None,
        from_webhook: bool = False,
    ) -> tuple[bool, bool, bool]:
        result = await self.db.execute(
            select(Requirement).where(
                Requirement.project_id == connection.project_id,
                Requirement.requirement_id == issue.key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is None:
            requirement = Requirement(
                project_id=connection.project_id,
                created_by=user_id,
                requirement_id=issue.key,
                source="jira",
                title=issue.summary,
                summary=issue.description,
                jira_issue_key=issue.key,
                jira_issue_type=issue.issue_type,
                jira_priority=issue.priority,
                jira_deleted=False,
                jira_updated_at=parse_jira_datetime(issue.updated),
                jira_last_synced_at=now_utc(),
                status="pending_approval",
                metadata_={"jira": _safe_issue_metadata(issue)},
            )
            self.db.add(requirement)
            await self.db.flush()
            return True, False, False

        conflicted = await self._has_concurrent_modification(existing, issue)
        if conflicted:
            await self._create_conflict_record(connection, existing, issue, sync_history_id)
            return False, False, True

        self._apply_issue(existing, issue)
        existing.status = "pending_approval" if from_webhook or existing.status == "draft" else existing.status
        existing.jira_deleted = False
        existing.jira_updated_at = parse_jira_datetime(issue.updated)
        existing.jira_last_synced_at = now_utc()
        await self.db.flush()
        return False, True, False

    async def _has_concurrent_modification(self, requirement: Requirement, issue: JiraIssueOut) -> bool:
        remote_updated = parse_jira_datetime(issue.updated)
        if not requirement.updated_at or not requirement.jira_last_synced_at or not remote_updated:
            return False
        return requirement.updated_at > requirement.jira_last_synced_at and remote_updated > requirement.jira_last_synced_at

    async def _create_conflict_record(
        self,
        connection: JiraConnection,
        requirement: Requirement,
        issue: JiraIssueOut,
        sync_history_id: int | None,
    ) -> ConflictRecord:
        result = await self.db.execute(
            select(ConflictRecord).where(
                ConflictRecord.connection_id == connection.id,
                ConflictRecord.jira_issue_key == issue.key,
                ConflictRecord.status == "open",
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.local_snapshot = _requirement_snapshot(requirement)
            existing.remote_snapshot = issue.model_dump(mode="json", exclude={"raw"})
            await self.db.flush()
            return existing
        conflict = ConflictRecord(
            project_id=connection.project_id,
            connection_id=connection.id,
            requirement_id=requirement.id,
            sync_history_id=sync_history_id,
            jira_issue_key=issue.key,
            conflict_type="concurrent_modification",
            status="open",
            local_snapshot=_requirement_snapshot(requirement),
            remote_snapshot=issue.model_dump(mode="json", exclude={"raw"}),
        )
        self.db.add(conflict)
        await self.db.flush()
        return conflict

    async def _upsert_requirement_from_issue(
        self,
        *,
        connection: JiraConnection,
        issue: JiraIssueOut,
        user_id: int,
    ) -> tuple[bool, Requirement]:
        result = await self.db.execute(
            select(Requirement).where(
                Requirement.project_id == connection.project_id,
                Requirement.requirement_id == issue.key,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            self._apply_issue(existing, issue)
            if existing.status == "draft":
                existing.status = "pending_review"
            await self.db.flush()
            return False, existing

        requirement = Requirement(
            project_id=connection.project_id,
            created_by=user_id,
            requirement_id=issue.key,
            source="jira",
            title=issue.summary,
            summary=issue.description,
            jira_issue_key=issue.key,
            jira_issue_type=issue.issue_type,
            jira_priority=issue.priority,
            status="pending_review",
            metadata_={"jira": _safe_issue_metadata(issue)},
        )
        try:
            begin_nested = getattr(self.db, "begin_nested", None)
            if begin_nested is None:
                self.db.add(requirement)
                await self.db.flush()
            else:
                async with self.db.begin_nested():
                    self.db.add(requirement)
                    await self.db.flush()
        except IntegrityError:
            result = await self.db.execute(
                select(Requirement).where(
                    Requirement.project_id == connection.project_id,
                    Requirement.requirement_id == issue.key,
                )
            )
            concurrent = result.scalar_one_or_none()
            if concurrent is None:
                raise
            self._apply_issue(concurrent, issue)
            if concurrent.status == "draft":
                concurrent.status = "pending_review"
            await self.db.flush()
            return False, concurrent
        await self.db.refresh(requirement)
        return True, requirement

    def _apply_issue(self, requirement: Requirement, issue: JiraIssueOut) -> None:
        requirement.title = _truncate(issue.summary, 500, issue.key)
        requirement.summary = issue.description
        requirement.jira_issue_key = issue.key
        requirement.jira_issue_type = _truncate(issue.issue_type, 100, "") or None
        requirement.jira_priority = _truncate(issue.priority, 50, "") or None
        metadata = dict(requirement.metadata_ or {})
        metadata["jira"] = _safe_issue_metadata(issue)
        requirement.metadata_ = metadata

    async def _search_page_for_number(
        self,
        connection: JiraConnection,
        jql: str,
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        next_page_token: str | None = None
        data: dict[str, Any] = {}
        for _ in range(page):
            data = await self._search(
                connection,
                jql,
                next_page_token=next_page_token,
                max_results=page_size,
            )
            next_page_token = data.get("nextPageToken")
            if data.get("isLast", not next_page_token):
                break
        return data

    async def _search(
        self,
        connection: JiraConnection,
        jql: str,
        *,
        next_page_token: str | None,
        max_results: int,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "jql": jql,
            "maxResults": max_results,
            "fields": "summary,description,issuetype,status,priority,labels,updated",
        }
        if next_page_token:
            params["nextPageToken"] = next_page_token
        return await self._request(
            connection,
            "GET",
            "/rest/api/3/search/jql",
            params=params,
            token=self.decrypt_token(connection),
        )

    async def _request(
        self,
        connection: JiraConnection,
        method: str,
        path: str,
        *,
        token: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self.http_client
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=30)
            close_client = True
        try:
            response = await client.request(
                method,
                f"{connection.jira_base_url}{path}",
                params=params,
                json=json,
                auth=(connection.jira_email, token),
                headers={"Accept": "application/json"},
            )
            if response.status_code >= 400:
                detail = _jira_error_message(response)
                raise HTTPException(status_code=502, detail=f"Jira request failed: {detail}")
            if response.status_code == 204 or not response.content:
                return {}
            try:
                payload = response.json()
            except ValueError as exc:
                raise HTTPException(status_code=502, detail="Jira returned a non-JSON response") from exc
            if not isinstance(payload, dict):
                raise HTTPException(status_code=502, detail="Jira returned an unexpected response shape")
            return payload
        except httpx.HTTPError as exc:
            # SEC-051: Log detailed network error server-side; return generic message to client
            logger.warning("Jira network error: %s", exc)
            raise HTTPException(status_code=502, detail="Could not connect to Jira — check your Jira base URL and network connectivity") from exc
        finally:
            if close_client:
                await client.aclose()


def _jira_error_message(response: httpx.Response) -> str:
    """
    SEC-051: Return a sanitized, client-safe error message.
    Detailed Jira response bodies are logged server-side only.
    """
    status = response.status_code
    # Log full detail server-side for diagnostics
    try:
        raw_detail = response.text[:500]
    except Exception:
        raw_detail = "<unreadable>"
    logger.warning("Jira API error: HTTP %d — %s", status, raw_detail)

    # Return only safe, generic messages to the caller
    if status == 400:
        return "Bad request sent to Jira — check your configuration and filters"
    if status == 401:
        return "Jira authentication failed — verify your API token"
    if status == 403:
        return "Access denied by Jira — check project permissions for your account"
    if status == 404:
        return "Jira resource not found — verify project key and issue types"
    if status == 429:
        return "Jira rate limit exceeded — please try again later"
    if status >= 500:
        return "Jira service error — try again or contact your Jira administrator"
    return f"Jira request failed with status {status}"


def _safe_issue_metadata(issue: JiraIssueOut) -> dict[str, Any]:
    return {
        "key": issue.key,
        "status": issue.status,
        "labels": issue.labels,
        "updated": issue.updated,
    }


def _requirement_snapshot(requirement: Requirement) -> dict[str, Any]:
    return {
        "id": requirement.id,
        "requirement_id": requirement.requirement_id,
        "title": requirement.title,
        "summary": requirement.summary,
        "status": requirement.status,
        "jira_updated_at": requirement.jira_updated_at.isoformat() if requirement.jira_updated_at else None,
        "jira_last_synced_at": requirement.jira_last_synced_at.isoformat() if requirement.jira_last_synced_at else None,
        "updated_at": requirement.updated_at.isoformat() if requirement.updated_at else None,
    }


def now_utc():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def datetime_iso() -> str:
    return now_utc().isoformat()
