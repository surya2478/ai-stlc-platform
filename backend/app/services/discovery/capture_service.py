"""Guided User Recording step-loop body (Phase 1).

Reuses the same Playwright-via-MCP transport as `mcp_discovery_agent.py` /
`grounded_capture_agent.py` (per the plan's reuse table) rather than a new
browser stack. What Phase 1 actually grounds per approved test step is a
real navigate + accessibility snapshot + screenshot — the honest subset the
existing infrastructure can perform without guessing at click targets a
recording adapter would normally supply. Guided User Recording's click/type
capture through a browser-side recording adapter is explicitly Phase 2+
backlog (see the implementation plan) — this module never fabricates a
click/type action it did not actually observe.

Every persisted evidence path lives under the managed discovery workspace
root, never a guessed location, and every screenshot capture uses the same
CWD-leak workaround as GroundedCaptureAgent (`@playwright/mcp`'s
`browser_take_screenshot` ignores `--output-dir` and any directory
component in `filename`).
"""
from __future__ import annotations

import hashlib
import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.automation.mcp_session import MCPSession, MCPSessionConfig, mask_snapshot_text
from app.models.discovery_session import DiscoveryAction, DiscoveryCapture, DiscoveryCheckpoint, DiscoverySession
from app.models.project_application import ProjectApplication
from app.models.test_case import TestCase
from app.services import locator_map_service
from app.services.discovery import locator_ranking

logger = logging.getLogger(__name__)


def discovery_workspace_root() -> Path:
    from app.services.automation_runner.workspace import workspace_root

    return workspace_root().parent / "discovery_workspace"


def session_output_dir(session_id: int) -> Path:
    path = discovery_workspace_root() / str(session_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


async def build_session_config(db: AsyncSession, session: DiscoverySession) -> MCPSessionConfig:
    output_dir = session_output_dir(session.id)
    return MCPSessionConfig(
        allowed_hosts=list(session.allowed_hosts or []), headless=True, output_dir=str(output_dir),
    )


async def _capture_screenshot(mcp_session: MCPSession, output_dir: Path, *, label: str) -> str | None:
    leak_name = f"discovery_{uuid.uuid4().hex}.png"
    await mcp_session.call("browser_take_screenshot", {"filename": leak_name})
    leaked_path = Path.cwd() / leak_name
    if not leaked_path.exists():
        return None
    target_path = output_dir / f"{label}.png"
    shutil.move(str(leaked_path), str(target_path))
    return str(target_path)


def _checksum(path: str | None) -> str | None:
    if not path:
        return None
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


async def start_capture(db: AsyncSession, session: DiscoverySession) -> tuple[MCPSession, Path, str | None]:
    """Opens the MCPSession and navigates to the environment's starting URL.
    Returns the open session (caller keeps it open across the step loop),
    the workspace dir, and the resolved starting URL (None if unresolvable —
    caller must fail the session rather than guess a URL)."""
    application = await db.get(ProjectApplication, session.application_id)
    url = (application.environment_urls or {}).get(session.environment) if application else None
    output_dir = session_output_dir(session.id)
    config = await build_session_config(db, session)
    mcp_session = MCPSession(config)
    await mcp_session.__aenter__()
    if url:
        await mcp_session.navigate(url)
    return mcp_session, output_dir, url


async def _capture_optional_evidence(
    db: AsyncSession, session: DiscoverySession, mcp_session: MCPSession, output_dir: Path, *,
    action: DiscoveryAction, label: str, now: datetime,
) -> list[int]:
    """Best-effort console/network evidence for one action (Phase 4) —
    gated independently by `session.capture_options`, defaulting to on (the
    P1-S4 contract's "capture ... network, APIs, console"). A fetch failure
    here is logged and skipped, same as every other best-effort capture in
    this module — it never fails the action itself."""
    capture_options = session.capture_options or {}
    ids: list[int] = []

    if capture_options.get("console_capture", True):
        try:
            raw = mask_snapshot_text(await mcp_session.console_messages(level="info"))
            path = output_dir / f"{label}_console.txt"
            path.write_text(raw, encoding="utf-8")
            capture = DiscoveryCapture(
                session_id=session.id, project_id=session.project_id, action_id=action.id,
                capture_type="console_log", storage_path=str(path), checksum=_checksum(str(path)),
                source="playwright_mcp", captured_at=now, redaction_state="applied",
            )
            db.add(capture)
            await db.flush()
            ids.append(capture.id)
        except Exception:
            logger.warning("capture_service: console capture failed for session %s", session.id, exc_info=True)

    if capture_options.get("network_capture", True):
        try:
            raw = mask_snapshot_text(await mcp_session.network_requests(static=False))
            path = output_dir / f"{label}_network.txt"
            path.write_text(raw, encoding="utf-8")
            capture = DiscoveryCapture(
                session_id=session.id, project_id=session.project_id, action_id=action.id,
                capture_type="network_log", storage_path=str(path), checksum=_checksum(str(path)),
                source="playwright_mcp", captured_at=now, redaction_state="applied",
            )
            db.add(capture)
            await db.flush()
            ids.append(capture.id)
        except Exception:
            logger.warning("capture_service: network capture failed for session %s", session.id, exc_info=True)

    return ids


async def _capture_evidence_and_persist_action(
    db: AsyncSession, session: DiscoverySession, mcp_session: MCPSession, output_dir: Path, *,
    actor: str, action_family: str, target_semantic: str, sequence: int, label: str,
    test_step_ref: str | None = None, input_binding: dict | None = None,
    provenance_call: str = "browser_snapshot", target_ref: str | None = None,
) -> DiscoveryAction:
    """Shared evidence-capture body for one real action: a snapshot +
    screenshot around whatever the caller already did (or is about to
    describe), persisted as one DiscoveryAction + DiscoveryCapture pair,
    plus (Phase 4) ranked/live-validated locator candidates for click/input
    actions and best-effort console/network captures. Used by both the
    Guided step-walk (`capture_one_step`) and Free/Agent-Driven mode's
    user-driven actions — the evidence contract is identical, only who
    decided the action (system vs. user) differs.
    """
    raw_snapshot = await mcp_session.snapshot()
    masked_snapshot = mask_snapshot_text(raw_snapshot)
    screenshot_path = await _capture_screenshot(mcp_session, output_dir, label=label)
    now = datetime.now(timezone.utc)

    locator_result = None
    if action_family in ("click", "input") and target_ref:
        try:
            locator_result = await locator_ranking.rank_and_validate(
                mcp_session, raw_snapshot=raw_snapshot, target_ref=target_ref,
                target_semantic=target_semantic, action_family=action_family,
            )
        except Exception:
            logger.warning("capture_service: locator ranking failed for session %s", session.id, exc_info=True)
    top_candidate = locator_result["candidates"][0] if locator_result and locator_result["candidates"] else None

    action = DiscoveryAction(
        session_id=session.id,
        project_id=session.project_id,
        sequence=sequence,
        actor=actor,
        test_step_ref=test_step_ref,
        action_family=action_family,
        target_semantic=target_semantic[:300],
        input_binding=input_binding,
        occurred_at=now,
        post_state={"accessibility_snapshot_excerpt": masked_snapshot[:4000]},
        inclusion_state="included",
        provenance={"tool": "playwright_mcp", "call": provenance_call},
        locator_evidence=locator_result,
        locator_confidence=top_candidate["confidence"] if top_candidate else None,
    )
    db.add(action)
    await db.flush()

    evidence_ids: list[int] = []
    if screenshot_path:
        capture = DiscoveryCapture(
            session_id=session.id, project_id=session.project_id, action_id=action.id,
            capture_type="screenshot", storage_path=screenshot_path, checksum=_checksum(screenshot_path),
            source="playwright_mcp", captured_at=now, redaction_state="not_required",
        )
        db.add(capture)
        await db.flush()
        evidence_ids.append(capture.id)

    if action_family in ("click", "input", "navigate"):
        evidence_ids += await _capture_optional_evidence(
            db, session, mcp_session, output_dir, action=action, label=label, now=now,
        )

    if evidence_ids:
        action.evidence_refs = evidence_ids

    if top_candidate:
        try:
            fallback_locator = (
                locator_result["candidates"][1]["locator"] if len(locator_result["candidates"]) > 1 else None
            )
            await locator_map_service.upsert_locator(
                db, project_id=session.project_id, application_id=session.application_id,
                page=locator_result.get("page_url") or "", element_name=locator_result["element_name"],
                recommended_locator=top_candidate["locator"], recommended_strategy=top_candidate["strategy"],
                fallback_locator=fallback_locator, confidence_score=top_candidate["confidence"],
            )
        except Exception:
            logger.warning("capture_service: locator_map upsert failed for session %s", session.id, exc_info=True)

    await db.flush()
    return action


async def _get_steps(db: AsyncSession, session: DiscoverySession) -> list:
    test_case = await db.get(TestCase, session.test_case_id) if session.test_case_id else None
    return (test_case.steps or []) if test_case else []


def _step_text(step) -> str:
    return step.get("action") or step.get("description") or str(step) if isinstance(step, dict) else str(step)


def _step_ref(step) -> str | None:
    return str(step.get("step_number")) if isinstance(step, dict) and step.get("step_number") else None


async def get_current_step(db: AsyncSession, session: DiscoverySession) -> dict | None:
    """The step a Guided/Agent-Driven session would act on next, without
    executing anything — used by Agent-Driven mode to show what it's about
    to propose (Section 11.1's "current step, expected application state")
    before the user approves/modifies/skips it."""
    steps = await _get_steps(db, session)
    if session.current_step_index >= len(steps):
        return None
    step = steps[session.current_step_index]
    return {"text": _step_text(step), "step_ref": _step_ref(step)}


async def capture_one_step(
    db: AsyncSession, session: DiscoverySession, mcp_session: MCPSession, output_dir: Path, *, actor: str = "system",
) -> DiscoveryAction | None:
    """Captures real evidence (snapshot + screenshot) for the current guided
    step and advances `current_step_index`. Returns None once every step has
    been captured. `actor` defaults to "system" (Guided mode's unsupervised
    auto-walk) — Agent-Driven's `approve_next_action` passes "agent" since
    the same step is instead proposed and only executed once approved."""
    steps = await _get_steps(db, session)
    if session.current_step_index >= len(steps):
        return None

    step = steps[session.current_step_index]

    action = await _capture_evidence_and_persist_action(
        db, session, mcp_session, output_dir,
        actor=actor, action_family="read", target_semantic=_step_text(step),
        sequence=session.current_step_index, label=f"step_{session.current_step_index}",
        test_step_ref=_step_ref(step),
    )
    session.current_step_index += 1
    await db.flush()
    return action


async def skip_current_step(db: AsyncSession, session: DiscoverySession, *, reason: str) -> DiscoveryAction | None:
    """Agent-Driven "Skip Next Action" (Section 10, reason required) —
    records that the approved step was deliberately not performed. No
    MCPSession call, no screenshot: nothing happened in the browser, so no
    evidence is fabricated for it."""
    steps = await _get_steps(db, session)
    if session.current_step_index >= len(steps):
        return None
    step = steps[session.current_step_index]
    now = datetime.now(timezone.utc)
    action = DiscoveryAction(
        session_id=session.id, project_id=session.project_id, sequence=session.current_step_index,
        actor="user", test_step_ref=_step_ref(step), action_family="read",
        target_semantic=_step_text(step)[:300], occurred_at=now,
        inclusion_state="skipped", issue_note=reason,
        provenance={"tool": "supervision", "call": "skip_action"},
    )
    db.add(action)
    await db.flush()
    session.current_step_index += 1
    await db.flush()
    return action


# ── Free User-Action Recording (Phase 2) ─────────────────────────────────

FREE_ACTION_FAMILIES = ("navigate", "click", "input", "read")

# Heuristic only (no secure-input semantic exists in the MCP transport yet —
# Section 16's "support secure-input semantic actions" is aspirational future
# work). Matches on the human-supplied element description, not the typed
# value, since the value is exactly what must never be persisted for these.
_SENSITIVE_FIELD_HINTS = ("password", "otp", "pin", "cvv", "cvc", "card number", "secret", "token")


def _is_sensitive_field(target_semantic: str | None) -> bool:
    text = (target_semantic or "").lower()
    return any(hint in text for hint in _SENSITIVE_FIELD_HINTS)


class FreeActionError(ValueError):
    """A Free-mode action request was malformed or not executable — reported
    back to the caller as a recorded failure event, never silently dropped."""


async def _execute_action_family(
    mcp_session: MCPSession, *, action_family: str,
    target_ref: str | None, target_semantic: str | None, input_text: str | None, url: str | None,
) -> tuple[str, dict | None]:
    """Performs one real browser call for the given action_family and
    returns (semantic description, sanitized input_binding). Shared by
    Free mode's `perform_free_action` and Agent-Driven's
    `perform_modified_step` — both let the user name a concrete action
    (never inferred/guessed), only who's allowed to invoke it and what
    happens to the step queue afterward differs.
    """
    if action_family not in FREE_ACTION_FAMILIES:
        raise FreeActionError(f"Unsupported action_family '{action_family}'")

    if action_family == "navigate":
        if not url:
            raise FreeActionError("navigate requires 'url'")
        await mcp_session.navigate(url)  # raises MCPSecurityError if host not allowed
        return target_semantic or f"Navigate to {url}", {"url": url}
    if action_family == "click":
        if not target_ref:
            raise FreeActionError("click requires 'target_ref'")
        await mcp_session.click(element=target_semantic or target_ref, target=target_ref)
        return target_semantic or f"Click {target_ref}", {"target_ref": target_ref}
    if action_family == "input":
        if not target_ref or input_text is None:
            raise FreeActionError("input requires 'target_ref' and 'input_text'")
        if _is_sensitive_field(target_semantic) or _is_sensitive_field(target_ref):
            persisted_text = "[REDACTED - sensitive field]"
        else:
            persisted_text = mask_snapshot_text(input_text)[:500]
        await mcp_session.type_text(element=target_semantic or target_ref, target=target_ref, text=input_text)
        return target_semantic or f"Type into {target_ref}", {"target_ref": target_ref, "text": persisted_text}
    # "read" — an explicit observation, no browser interaction
    return target_semantic or "Observed current state", None


async def _next_action_sequence(db: AsyncSession, session: DiscoverySession) -> int:
    result = await db.execute(
        select(DiscoveryAction.sequence)
        .where(DiscoveryAction.session_id == session.id)
        .order_by(DiscoveryAction.sequence.desc())
        .limit(1)
    )
    existing_max_sequence = result.scalar_one_or_none()
    # `existing_max_sequence or -1` would be wrong here: 0 is a legitimate
    # first sequence number, and `0 or -1` evaluates to -1 in Python (0 is
    # falsy), which silently reused sequence 0 for every action instead of
    # incrementing — caught live when a second Free-mode action got
    # persisted with the same sequence as the first.
    return (existing_max_sequence + 1) if existing_max_sequence is not None else 0


async def perform_free_action(
    db: AsyncSession, session: DiscoverySession, mcp_session: MCPSession, output_dir: Path, *,
    action_family: str,
    target_ref: str | None = None,
    target_semantic: str | None = None,
    input_text: str | None = None,
    url: str | None = None,
) -> DiscoveryAction:
    """Performs exactly one user-directed action against the real live
    browser session (Section 5.2 — "user actions are captured without an
    approved step plan"). Every action here is one the user explicitly
    named (a URL to navigate to, an element ref to click/type into, read
    from the last snapshot) — nothing is inferred or guessed on their
    behalf; `MCPSession.navigate`'s existing allowed-host check is the same
    single security boundary Guided mode relies on.
    """
    semantic, input_binding = await _execute_action_family(
        mcp_session, action_family=action_family, target_ref=target_ref,
        target_semantic=target_semantic, input_text=input_text, url=url,
    )
    next_sequence = await _next_action_sequence(db, session)

    return await _capture_evidence_and_persist_action(
        db, session, mcp_session, output_dir,
        actor="user", action_family=action_family, target_semantic=semantic,
        sequence=next_sequence, label=f"free_{next_sequence}",
        input_binding=input_binding, provenance_call=f"browser_{action_family}", target_ref=target_ref,
    )


async def perform_modified_step(
    db: AsyncSession, session: DiscoverySession, mcp_session: MCPSession, output_dir: Path, *,
    action_family: str,
    target_ref: str | None = None,
    target_semantic: str | None = None,
    input_text: str | None = None,
    url: str | None = None,
) -> DiscoveryAction | None:
    """Agent-Driven "Modify Next Action" (Section 10) — the user substitutes
    a concrete action for the currently proposed approved step instead of
    approving it as-is. The step's own text in the approved test case is
    never mutated (Section 3.1 — "approved steps are immutable during
    execution"); this only records what was actually done, tagged
    `corrected` and linked back to the step by `test_step_ref`, exactly the
    same "reviewed capture change" the contract calls for.
    """
    steps = await _get_steps(db, session)
    if session.current_step_index >= len(steps):
        return None
    step = steps[session.current_step_index]

    semantic, input_binding = await _execute_action_family(
        mcp_session, action_family=action_family, target_ref=target_ref,
        target_semantic=target_semantic, input_text=input_text, url=url,
    )

    action = await _capture_evidence_and_persist_action(
        db, session, mcp_session, output_dir,
        actor="user", action_family=action_family, target_semantic=semantic,
        sequence=session.current_step_index, label=f"step_{session.current_step_index}_modified",
        test_step_ref=_step_ref(step), input_binding=input_binding,
        provenance_call=f"browser_{action_family}", target_ref=target_ref,
    )
    action.inclusion_state = "corrected"
    action.correction_history = [{
        "previous_inclusion_state": "included",
        "new_inclusion_state": "corrected",
        "reason": f"Modified from proposed step: {_step_text(step)[:200]}",
    }]
    session.current_step_index += 1
    await db.flush()
    return action


async def create_checkpoint(
    db: AsyncSession, session: DiscoverySession, *, state_at_checkpoint: str, created_by_actor: str = "system",
    resumable: bool = True,
) -> DiscoveryCheckpoint:
    result = await db.execute(
        select(DiscoveryAction.target_semantic)
        .where(DiscoveryAction.session_id == session.id)
        .order_by(DiscoveryAction.sequence.desc())
        .limit(1)
    )
    last_screen = result.scalar_one_or_none()

    result = await db.execute(select(DiscoveryCheckpoint.sequence).where(DiscoveryCheckpoint.session_id == session.id))
    next_sequence = (max([r for r in result.scalars().all()], default=-1)) + 1

    application = await db.get(ProjectApplication, session.application_id)
    url = (application.environment_urls or {}).get(session.environment) if application else None
    sanitized_url = urlparse(url).netloc + urlparse(url).path if url else None

    checkpoint = DiscoveryCheckpoint(
        session_id=session.id, project_id=session.project_id, sequence=next_sequence,
        state_at_checkpoint=state_at_checkpoint, action_position=session.current_step_index,
        sanitized_url=sanitized_url, sanitized_screen=last_screen,
        resumable=resumable, created_by_actor=created_by_actor,
    )
    db.add(checkpoint)
    await db.flush()
    session.latest_checkpoint_id = checkpoint.id
    await db.flush()
    return checkpoint


async def close_capture(mcp_session: MCPSession) -> None:
    await mcp_session.__aexit__(None, None, None)
