"""UI-017 API and Network Explorer — Phase 1 build + review service.

`build_or_rebuild` parses a `DiscoverySession`'s masked `network_log`
`DiscoveryCapture` text files (one per action, written verbatim from the
Playwright MCP `browser_network_requests` tool by
`capture_service._capture_optional_evidence`) into structured `NetworkEvent`
rows — the only structured signal this capture pipeline can honestly
produce today: method, URL, host/path and status. Headers, request/response
bodies and timing are never available from this tool, so this service never
invents them; a line the parser can't confidently read is kept with
`parse_state="unparsed"` and its already-masked raw text, exactly the same
"never guess" discipline `application_model_service.py` uses for gaps.

Rebuild-in-place (delete then re-derive) rather than merge, same rationale
as `build_or_rebuild_draft`: a rebuild must reflect the session's current
captures exactly, not accumulate stale rows across repeated builds.
"""
from __future__ import annotations

import os
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery_session import DiscoveryCapture, DiscoverySession
from app.models.network_event import NetworkEvent, NetworkEventActivity
from app.models.project_application import ProjectApplication

# One request line as written by capture_service (masked, verbatim MCP tool
# output): "N. [METHOD] url => [status] statusText" — the real
# `browser_network_requests` tool numbers each entry ("5. [GET] ...",
# "12. [GET] ..."). The response half is absent for a request still pending
# when the snapshot was taken, and non-request lines (headers, "### Result",
# the trailing "N static requests not shown" note) never match at all.
_LINE_RE = re.compile(
    r"^\s*(?:\d+\.\s+|[-*]\s*)?\[(?P<method>[A-Za-z]+)\]\s+(?P<url>\S+)"
    r"(?:\s*=>\s*\[(?P<status>\d{3})\](?:\s+(?P<statustext>[^\n]*))?)?\s*$"
)


class NetworkEventError(HTTPException):
    def __init__(self, status_code: int, code: str, message: str):
        super().__init__(status_code=status_code, detail={"code": code, "message": message})


def _parse_line(line: str) -> dict[str, Any]:
    match = _LINE_RE.match(line)
    if not match:
        return {"parse_state": "unparsed"}
    url = match.group("url")
    parsed_url = urlparse(url)
    status = match.group("status")
    return {
        "parse_state": "parsed",
        "method": match.group("method").upper(),
        "url": url,
        "host": parsed_url.netloc or None,
        "path": parsed_url.path or None,
        "status_code": int(status) if status else None,
        "status_text": (match.group("statustext") or "").strip() or None,
    }


def _read_capture_text(capture: DiscoveryCapture) -> str | None:
    """Same managed-workspace-root containment check as
    `discovery.get_capture_content` — never read outside it."""
    from app.services.discovery.capture_service import discovery_workspace_root

    storage_root = os.path.realpath(discovery_workspace_root())
    real_path = os.path.realpath(capture.storage_path)
    if not (real_path.startswith(storage_root + os.sep) or real_path == storage_root):
        return None
    if not os.path.exists(real_path):
        return None
    with open(real_path, "r", encoding="utf-8") as f:
        return f.read()


async def _log_activity(
    db: AsyncSession, *, project_id: int, session_id: int, event_type: str, actor_id: int | None,
    event_id: int | None = None, reason: str | None = None, correlation_id: str | None = None,
) -> None:
    db.add(
        NetworkEventActivity(
            project_id=project_id, session_id=session_id, event_type=event_type, actor_id=actor_id,
            event_id=event_id, reason=reason, correlation_id=correlation_id,
        )
    )
    await db.flush()


async def get_session_or_404(db: AsyncSession, *, project_id: int, session_id: int) -> DiscoverySession:
    session = await db.get(DiscoverySession, session_id)
    if session is None or session.project_id != project_id:
        raise NetworkEventError(404, "SESSION_NOT_FOUND", "Discovery session not found in this project.")
    return session


async def get_session_by_id_or_404(db: AsyncSession, session_id: int) -> DiscoverySession:
    session = await db.get(DiscoverySession, session_id)
    if session is None:
        raise NetworkEventError(404, "SESSION_NOT_FOUND", "Discovery session not found.")
    return session


async def build_or_rebuild(db: AsyncSession, *, project_id: int, session_id: int, actor_id: int) -> DiscoverySession:
    session = await get_session_or_404(db, project_id=project_id, session_id=session_id)

    session_host: str | None = None
    application = await db.get(ProjectApplication, session.application_id)
    if application is not None:
        env_url = (application.environment_urls or {}).get(session.environment)
        if env_url:
            session_host = urlparse(env_url).netloc

    await db.execute(delete(NetworkEvent).where(NetworkEvent.session_id == session_id))
    await db.flush()

    captures_result = await db.execute(
        select(DiscoveryCapture)
        .where(DiscoveryCapture.session_id == session_id, DiscoveryCapture.capture_type == "network_log")
        .order_by(DiscoveryCapture.captured_at, DiscoveryCapture.id)
    )
    captures = list(captures_result.scalars().all())

    sequence = 0
    for capture in captures:
        text = _read_capture_text(capture)
        if not text:
            continue
        for raw_line in text.splitlines():
            if not raw_line.strip():
                continue
            parsed = _parse_line(raw_line)
            host = parsed.get("host")
            is_external = (host != session_host) if (parsed.get("parse_state") == "parsed" and host and session_host) else None
            db.add(
                NetworkEvent(
                    project_id=project_id, session_id=session_id, capture_id=capture.id, action_id=capture.action_id,
                    sequence=sequence, raw_line=raw_line[:2000], is_external=is_external, **parsed,
                )
            )
            sequence += 1

    await db.flush()
    await _log_activity(
        db, project_id=project_id, session_id=session_id, event_type="events_built", actor_id=actor_id,
        reason=f"Parsed {sequence} event(s) from {len(captures)} network-log capture(s).",
        correlation_id=session.correlation_id,
    )
    await db.commit()
    return session


async def compute_kpis(db: AsyncSession, session_id: int) -> dict[str, Any]:
    result = await db.execute(select(NetworkEvent).where(NetworkEvent.session_id == session_id))
    events = list(result.scalars().all())
    parsed = [e for e in events if e.parse_state == "parsed"]
    apis = {(e.method, e.path) for e in parsed if e.method and e.path}
    external_hosts = {e.host for e in parsed if e.is_external and e.host}
    mapped = [e for e in events if e.action_id is not None]
    ignored = [e for e in events if e.review_state == "ignored"]
    return {
        "requests_captured": len(events),
        "requests_parsed": len(parsed),
        "requests_unparsed": len(events) - len(parsed),
        "apis_identified": len(apis),
        "external_systems": len(external_hosts),
        "mapping_readiness_pct": round(100 * len(mapped) / len(events)) if events else 0,
        "ignored": len(ignored),
        # No API/DB validator or external-MCP infrastructure exists yet
        # (UI-017 contract Sections 13/14) — never fabricate a pass/fail
        # count; the UI must show this as "not evaluated", not zero.
        "validation_available": False,
    }


async def get_event_or_404(db: AsyncSession, event_id: int) -> NetworkEvent:
    row = await db.get(NetworkEvent, event_id)
    if row is None:
        raise NetworkEventError(404, "EVENT_NOT_FOUND", "Network event not found.")
    return row


async def list_events(
    db: AsyncSession, *, session_id: int, method: str | None = None, status_bucket: str | None = None,
    external_only: bool = False, unmapped_only: bool = False, review_state: str | None = None,
    search: str | None = None,
) -> list[NetworkEvent]:
    query = select(NetworkEvent).where(NetworkEvent.session_id == session_id)
    if method:
        query = query.where(NetworkEvent.method == method.upper())
    if status_bucket == "2xx":
        query = query.where(NetworkEvent.status_code >= 200, NetworkEvent.status_code < 300)
    elif status_bucket == "3xx":
        query = query.where(NetworkEvent.status_code >= 300, NetworkEvent.status_code < 400)
    elif status_bucket == "4xx":
        query = query.where(NetworkEvent.status_code >= 400, NetworkEvent.status_code < 500)
    elif status_bucket == "5xx":
        query = query.where(NetworkEvent.status_code >= 500)
    if external_only:
        query = query.where(NetworkEvent.is_external.is_(True))
    if unmapped_only:
        query = query.where(NetworkEvent.action_id.is_(None))
    if review_state:
        query = query.where(NetworkEvent.review_state == review_state)
    if search:
        query = query.where(NetworkEvent.url.ilike(f"%{search}%"))
    result = await db.execute(query.order_by(NetworkEvent.sequence))
    return list(result.scalars().all())


async def mark_ignored(db: AsyncSession, event: NetworkEvent, *, actor_id: int, reason: str) -> NetworkEvent:
    if not reason or not reason.strip():
        raise NetworkEventError(422, "REASON_REQUIRED", "Marking a request ignored requires a reason.")
    event.review_state = "ignored"
    event.review_reason = reason
    event.reviewed_by = actor_id
    event.reviewed_at = datetime.now(timezone.utc)
    await _log_activity(
        db, project_id=event.project_id, session_id=event.session_id, event_type="event_ignored",
        actor_id=actor_id, event_id=event.id, reason=reason,
    )
    await db.commit()
    await db.refresh(event)
    return event


async def mark_reviewed(db: AsyncSession, event: NetworkEvent, *, actor_id: int, note: str | None) -> NetworkEvent:
    event.review_state = "reviewed"
    event.review_reason = note
    event.reviewed_by = actor_id
    event.reviewed_at = datetime.now(timezone.utc)
    await _log_activity(
        db, project_id=event.project_id, session_id=event.session_id, event_type="event_reviewed",
        actor_id=actor_id, event_id=event.id, reason=note,
    )
    await db.commit()
    await db.refresh(event)
    return event


async def list_activity(db: AsyncSession, session_id: int) -> list[NetworkEventActivity]:
    result = await db.execute(
        select(NetworkEventActivity)
        .where(NetworkEventActivity.session_id == session_id)
        .order_by(NetworkEventActivity.created_at.desc())
    )
    return list(result.scalars().all())
