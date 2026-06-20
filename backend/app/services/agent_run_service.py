"""Persistence helpers for agent run audit trails."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.agent import AgentLog, AgentRun


settings = get_settings()

VALID_LOG_LEVELS = {"debug", "info", "warning", "error", "critical"}
LOG_LEVEL_ALIASES = {"warn": "warning"}
DEFAULT_PROMPT_VERSION = "v1"
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|token|password|secret)=([^\s]+)"),
    re.compile(r'(?i)("?(?:api[_-]?key|token|password|secret)"?\s*:\s*")([^"]+)(")'),
    re.compile(r"(?i)(bearer\s+)[a-z0-9._\-]+"),
]


def _safe_mapping(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    return {"value": value}


def canonical_json(value: Any) -> str:
    return json.dumps(value or {}, sort_keys=True, separators=(",", ":"), default=str)


def input_hash(input_data: dict[str, Any] | None) -> str:
    return hashlib.sha256(canonical_json(input_data).encode("utf-8")).hexdigest()


def derive_idempotency_key(
    *,
    project_id: int,
    user_id: int,
    agent_name: str,
    input_data: dict[str, Any] | None,
    prompt_version: str | None = None,
) -> tuple[str, str]:
    digest = input_hash(input_data)
    raw = f"{project_id}:{user_id}:{agent_name}:{prompt_version or DEFAULT_PROMPT_VERSION}:{digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest(), digest


def sanitize_error(message: str | None) -> str:
    text = str(message or "Agent failed")
    for pattern in SENSITIVE_PATTERNS:
        if pattern.groups == 3:
            text = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]{match.group(3)}", text)
        else:
            text = pattern.sub(lambda match: f"{match.group(1)}[REDACTED]", text)
    return text[:2000]


def _normalise_log(log: Any) -> dict[str, Any]:
    if isinstance(log, str):
        return {"level": "info", "step": None, "message": log, "data": None}

    data = _safe_mapping(log) or {}
    level = str(data.get("level") or "info").lower()
    level = LOG_LEVEL_ALIASES.get(level, level)
    if level not in VALID_LOG_LEVELS:
        level = "info"

    message = data.get("message")
    if message is None:
        message = str(data)

    extra = data.get("data")
    if extra is not None and not isinstance(extra, dict):
        extra = {"value": extra}

    return {
        "level": level,
        "step": data.get("step"),
        "message": str(message),
        "data": extra,
    }


def _result_logs(agent_result: Any) -> list[Any]:
    if agent_result is None:
        return []
    if hasattr(agent_result, "logs"):
        return getattr(agent_result, "logs") or []
    if hasattr(agent_result, "collected_logs"):
        return getattr(agent_result, "collected_logs") or []
    return []


def _result_output(agent_result: Any) -> dict[str, Any] | None:
    if agent_result is None:
        return None
    if hasattr(agent_result, "data"):
        return _safe_mapping(getattr(agent_result, "data"))
    if hasattr(agent_result, "output"):
        return _safe_mapping(getattr(agent_result, "output"))
    return _safe_mapping(agent_result)


def _result_error(agent_result: Any) -> str | None:
    if agent_result is None:
        return None
    error = getattr(agent_result, "error", None)
    return str(error) if error else None


def _result_duration(agent_result: Any) -> float | None:
    duration = getattr(agent_result, "duration_seconds", None)
    return float(duration) if duration is not None else None


def _elapsed_seconds(created_at: datetime | None) -> float | None:
    if not created_at:
        return None
    now = datetime.now(created_at.tzinfo or timezone.utc)
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return max((now - created_at).total_seconds(), 0.0)


async def start_agent_run(
    db: AsyncSession,
    *,
    project_id: int,
    user_id: int,
    agent_name: str,
    input_data: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
    status: str = "running",
    idempotency_key: str | None = None,
    input_hash_value: str | None = None,
    prompt_version: str | None = None,
    progress_percent: int | None = None,
    progress_message: str | None = None,
) -> AgentRun:
    """Create and commit a running AgentRun before long-running work starts."""
    run = AgentRun(
        project_id=project_id,
        triggered_by=user_id,
        agent_name=agent_name,
        status=status,
        input_data=input_data,
        input_hash=input_hash_value,
        idempotency_key=idempotency_key,
        prompt_version=prompt_version or DEFAULT_PROMPT_VERSION,
        llm_provider=settings.default_llm_provider,
        llm_model=settings.default_llm_model,
        progress_percent=progress_percent if progress_percent is not None else (0 if status == "pending" else 10),
        progress_message=progress_message or ("Queued" if status == "pending" else "Started"),
        metadata_=metadata,
    )
    db.add(run)
    await db.flush()
    step = "queued" if status == "pending" else "start"
    message = f"Agent '{agent_name}' queued" if status == "pending" else f"Agent '{agent_name}' started"
    await add_log(db, run, level="info", step=step, message=message)
    await db.commit()
    await db.refresh(run)
    return run


async def find_agent_run_by_idempotency_key(
    db: AsyncSession,
    *,
    project_id: int,
    idempotency_key: str,
) -> AgentRun | None:
    result = await db.execute(
        select(AgentRun).where(
            AgentRun.project_id == project_id,
            AgentRun.idempotency_key == idempotency_key,
        )
    )
    return result.scalar_one_or_none()


async def update_progress(
    db: AsyncSession,
    run: AgentRun,
    *,
    percent: int,
    message: str,
    step: str | None = "progress",
) -> AgentRun:
    run.progress_percent = max(0, min(100, int(percent)))
    run.progress_message = message[:500]
    await add_log(db, run, level="info", step=step, message=run.progress_message)
    await db.flush()
    return run


async def add_log(
    db: AsyncSession,
    run: AgentRun,
    *,
    level: str,
    message: str,
    step: str | None = None,
    data: dict[str, Any] | None = None,
) -> AgentLog:
    entry = AgentLog(
        agent_run_id=run.id,
        project_id=run.project_id,
        level=level if level in VALID_LOG_LEVELS else "info",
        step=step,
        message=message,
        data=data,
    )
    db.add(entry)
    await db.flush()
    return entry


async def add_logs(db: AsyncSession, run: AgentRun, logs: list[Any] | None) -> None:
    for raw_log in logs or []:
        log = _normalise_log(raw_log)
        await add_log(db, run, **log)


async def complete_agent_run(
    db: AsyncSession,
    run: AgentRun,
    *,
    agent_result: Any = None,
    output_data: dict[str, Any] | None = None,
) -> AgentRun:
    run.status = "completed"
    run.progress_percent = 100
    run.progress_message = "Completed"
    run.output_data = output_data if output_data is not None else _result_output(agent_result)
    run.error_message = None
    duration = _result_duration(agent_result)
    if duration is not None:
        run.duration_seconds = duration
    else:
        run.duration_seconds = _elapsed_seconds(run.created_at)
    await add_logs(db, run, _result_logs(agent_result))
    await add_log(db, run, level="info", step="complete", message=f"Agent '{run.agent_name}' completed")
    await db.flush()
    return run


async def fail_agent_run(
    db: AsyncSession,
    run_or_id: AgentRun | int,
    *,
    error_message: str,
    agent_result: Any = None,
    output_data: dict[str, Any] | None = None,
) -> AgentRun | None:
    if isinstance(run_or_id, int):
        result = await db.execute(select(AgentRun).where(AgentRun.id == run_or_id))
        run = result.scalar_one_or_none()
    else:
        run = run_or_id

    if not run:
        return None

    run.status = "failed"
    run.progress_message = "Failed"
    run.error_message = sanitize_error(error_message or _result_error(agent_result) or "Agent failed")
    run.output_data = output_data if output_data is not None else _result_output(agent_result)
    duration = _result_duration(agent_result)
    if duration is not None:
        run.duration_seconds = duration
    else:
        run.duration_seconds = _elapsed_seconds(run.created_at)
    await add_logs(db, run, _result_logs(agent_result))
    await add_log(db, run, level="error", step="failed", message=run.error_message)
    await db.flush()
    return run
