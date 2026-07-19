"""Grounded Automation PoC — TC-guided application-state capture agent.

Launches the target application in a real, isolated Playwright MCP browser
session (the existing MCPSession — same allowlist, audit-hook and
credential-isolation guarantees) and walks the test case's OWN journey step
by step, capturing one Application State Evidence Package per distinct
state reached: masked accessibility snapshot, ranked element catalog (with
live refs), screenshot, blockers, console errors, state fingerprint.

This is the deliberate upgrade over PlaywrightMCPDiscoveryAgent, whose walk
is entry-page + at most MAX_RELEVANT_LINKS(2) follow-ups: here the TC's
steps drive the traversal, bounded by grounded_capture_max_steps/minutes.

No LLM in the walk. Step→element matching is deterministic token overlap;
what cannot be matched confidently becomes either a pause (assisted mode —
the user picks from candidates) or a recorded gap (automated mode — the
coverage gate downstream will block generation and show exactly why).
Persistence happens in agent_tasks.py via grounded_poc_service, matching
every other agent in this codebase — this module only returns data.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.agents.automation.mcp_discovery_agent import _detect_live_blockers, _rank_elements
from app.agents.automation.mcp_session import (
    MCPSecurityError,
    MCPSession,
    MCPSessionConfig,
    mask_snapshot_text,
)
from app.agents.automation.snapshot_parser import ParsedSnapshot, parse_snapshot
from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.config import get_settings
from app.services.automation_runner.readiness import ReadinessInputs, check_readiness
from app.services.automation_runner.workspace import workspace_root

logger = logging.getLogger(__name__)
settings = get_settings()

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = frozenset({
    "the", "and", "for", "with", "that", "this", "then", "page", "user",
    "should", "will", "into", "from", "value", "screen", "on", "in", "a", "an",
})
_NAVIGATION_RE = re.compile(r"\b(navigate|open|launch|go\s*to|visit|access)\b", re.IGNORECASE)
_FILL_RE = re.compile(r"\b(enter|fill|type|input|provide)\b", re.IGNORECASE)
_CLICK_RE = re.compile(r"\b(click|press|tap|submit|select|choose|check|toggle|expand)\b", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall((text or "").lower()) if len(w) > 2 and w not in _STOPWORDS}


def state_fingerprint(url: str | None, title: str | None, element_names: list[str]) -> str:
    """Application-state identity: same URL with different content hashes
    differently. Sequence is deliberately excluded so revisits dedupe."""
    payload = json.dumps({"url": url or "", "title": title or "", "elements": sorted(element_names)})
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _catalog_with_refs(parsed: ParsedSnapshot) -> list[dict]:
    """Discovery's ranked catalog, with the live snapshot ref re-attached.

    _rank_elements iterates parsed.interactive_elements in order and appends
    one entry per element, so a positional zip is exact — refs are needed to
    actually perform actions (browser_click targets a ref, not a locator).
    """
    ranked = _rank_elements(parsed)
    interactive = parsed.interactive_elements
    for entry, el in zip(ranked, interactive):
        entry["ref"] = el.ref
    return ranked


def _score_elements(step_text: str, catalog: list[dict], *, roles: set[str] | None = None) -> list[dict]:
    """All catalog elements scored by token overlap with the step text,
    best first. Optionally restricted to given roles."""
    step_tokens = _tokens(step_text)
    scored = []
    for el in catalog:
        if roles and el.get("role") not in roles:
            continue
        name_tokens = _tokens(str(el.get("accessible_name") or el.get("element_name") or ""))
        score = len(step_tokens & name_tokens)
        if score > 0:
            scored.append({**el, "match_score": score})
    scored.sort(key=lambda e: e["match_score"], reverse=True)
    return scored


def _data_value_for_step(step_text: str, test_data: dict | None) -> str | None:
    """Pick the test_data value a fill-step refers to (field-name token
    overlap; falls back to the single value if there is exactly one)."""
    data = test_data or {}
    if not data:
        return None
    step_lower = step_text.lower()
    for key, value in data.items():
        key_tokens = [t for t in _WORD_RE.findall(str(key).lower()) if len(t) > 2]
        if key_tokens and any(t in step_lower for t in key_tokens):
            return str(value)
    if len(data) == 1:
        return str(next(iter(data.values())))
    return None


class GroundedCaptureAgent(BaseAgent):
    """Walks a test case's journey through the live app, capturing
    Application State Evidence Packages for the coverage gate."""

    name = "grounded_capture"

    async def run(
        self,
        *,
        test_case: dict[str, Any],
        application_url: str,
        application_id: int | None = None,
        environment: str | None = None,
        capture_mode: str = "automated",
        routing: dict[str, Any] | None = None,
        confirmed_actions: dict[str, str] | None = None,
        max_steps: int | None = None,
        max_minutes: int | None = None,
    ) -> AgentRunResult:
        self._logs.clear()
        tc_id = test_case.get("test_case_id") or test_case.get("id")
        self.log("info", "start", f"Grounded capture for test case {tc_id} at {application_url}")

        if not application_url:
            return AgentRunResult(success=False, error="No application URL provided", data={}, logs=self._logs)

        readiness = await check_readiness(
            ReadinessInputs(application_url=application_url, framework="playwright")
        )
        if not readiness.ready:
            blockers = "; ".join(f"{c.name}: {c.detail}" for c in readiness.blockers)
            return AgentRunResult(
                success=False, error=f"Environment not ready: {blockers}", data={}, logs=self._logs
            )

        try:
            data = await self._walk(
                test_case=test_case,
                application_url=application_url,
                environment=environment,
                capture_mode=capture_mode,
                routing=routing or {},
                confirmed_actions={str(k): v for k, v in (confirmed_actions or {}).items()},
                max_steps=max_steps or settings.grounded_capture_max_steps,
                max_minutes=max_minutes or settings.grounded_capture_max_minutes,
            )
        except MCPSecurityError as exc:
            return AgentRunResult(success=False, error=f"Security policy blocked capture: {exc}", data={}, logs=self._logs)
        except Exception as exc:  # noqa: BLE001 — surfaced as run failure
            logger.exception("Grounded capture failed for test case %s", tc_id)
            return AgentRunResult(success=False, error=f"Capture failed: {exc}", data={}, logs=self._logs)

        data["application_id"] = application_id
        self.log(
            "info", "complete",
            f"Captured {len(data['states'])} state(s) across {len(data['step_trace'])} step(s)"
            + (" — paused for confirmation" if data.get("paused") else ""),
        )
        return AgentRunResult(success=True, data=data, logs=self._logs)

    async def _walk(
        self,
        *,
        test_case: dict[str, Any],
        application_url: str,
        environment: str | None,
        capture_mode: str,
        routing: dict[str, Any],
        confirmed_actions: dict[str, str],
        max_steps: int,
        max_minutes: int,
    ) -> dict[str, Any]:
        host = urlparse(application_url).hostname
        output_dir = workspace_root() / "grounded_capture" / uuid.uuid4().hex
        output_dir.mkdir(parents=True, exist_ok=True)
        config = MCPSessionConfig(allowed_hosts=[host] if host else [], output_dir=str(output_dir))

        async def audit(tool_name: str, arguments: dict, text: str) -> None:
            self.log("info", "mcp_call", tool_name, data={"masked_result_excerpt": mask_snapshot_text(text)[:500]})

        deadline = time.monotonic() + max_minutes * 60
        routing_steps = {r["index"]: r for r in routing.get("steps", [])}
        steps = test_case.get("steps") or []
        test_data = test_case.get("test_data") or {}

        states: list[dict] = []
        step_trace: list[dict] = []
        paused: dict | None = None
        seen_fingerprints: set[str] = set()

        async with MCPSession(config, on_call=audit) as session:
            raw = await session.navigate(application_url)
            raw = await session.snapshot()  # navigate may link a file; snapshot inlines
            parsed = parse_snapshot(raw)
            catalog = _catalog_with_refs(parsed)
            entry_state = await self._package(
                session, parsed, raw, catalog,
                sequence=0, produced_by_step=None, environment=environment, output_dir=output_dir,
            )
            states.append(entry_state)
            seen_fingerprints.add(entry_state["state_fingerprint"])

            for index, raw_step in enumerate(steps):
                if len(step_trace) >= max_steps:
                    step_trace.append({"step": index + 1, "outcome": "budget_exhausted",
                                       "detail": f"max_steps={max_steps} reached"})
                    break
                if time.monotonic() > deadline:
                    step_trace.append({"step": index + 1, "outcome": "budget_exhausted",
                                       "detail": f"max_minutes={max_minutes} reached"})
                    break

                action_text = (
                    str(raw_step.get("action") or raw_step.get("description") or "")
                    if isinstance(raw_step, dict) else str(raw_step)
                )
                route = (routing_steps.get(index) or {}).get("action_route") or {}
                if route.get("type") and route["type"] != "web_ui":
                    step_trace.append({
                        "step": index + 1, "outcome": "routed_non_ui",
                        "detail": f"Routed to {route.get('adapter')} — not walked in the browser",
                    })
                    continue

                trace, new_raw = await self._perform_step(
                    session, index=index, action_text=action_text, catalog=catalog,
                    test_data=test_data, capture_mode=capture_mode,
                    confirmed_element=confirmed_actions.get(str(index)),
                )
                step_trace.append(trace)

                if trace["outcome"] == "needs_confirmation":
                    paused = {
                        "step_index": index,
                        "action_text": action_text[:300],
                        "candidates": trace.get("candidates") or [],
                        "reason": trace.get("detail"),
                    }
                    break

                if new_raw is not None:
                    parsed = parse_snapshot(new_raw)
                    catalog = _catalog_with_refs(parsed)
                    package = await self._package(
                        session, parsed, new_raw, catalog,
                        sequence=len(states), produced_by_step=index,
                        environment=environment, output_dir=output_dir,
                    )
                    if package["state_fingerprint"] not in seen_fingerprints:
                        states.append(package)
                        seen_fingerprints.add(package["state_fingerprint"])
                        trace["state_changed"] = True
                    else:
                        trace["state_changed"] = False

        return {
            "application_url": application_url,
            "capture_mode": capture_mode,
            "states": states,
            "step_trace": step_trace,
            "paused": paused,
            "output_dir": str(output_dir),
        }

    async def _perform_step(
        self,
        session: MCPSession,
        *,
        index: int,
        action_text: str,
        catalog: list[dict],
        test_data: dict,
        capture_mode: str,
        confirmed_element: str | None,
    ) -> tuple[dict, str | None]:
        """Try to execute one TC step against the live page. Returns
        (trace, raw_snapshot_after_action | None)."""
        trace: dict[str, Any] = {"step": index + 1, "action_text": action_text[:200]}

        is_fill = bool(_FILL_RE.search(action_text))
        is_click = bool(_CLICK_RE.search(action_text))
        if _NAVIGATION_RE.search(action_text) and not is_fill and not is_click:
            # Pure navigation: try a matching link; otherwise the current
            # (already captured) state is the destination.
            links = _score_elements(action_text, catalog, roles={"link"})
            if links and links[0].get("ref"):
                target = links[0]
                await session.click(element=target.get("accessible_name") or "link", target=target["ref"])
                trace.update({"outcome": "navigated", "element": target["element_name"]})
                return trace, await session.snapshot()
            trace.update({"outcome": "already_on_state", "detail": "Navigation step; no link matched — current state stands"})
            return trace, None

        candidates = _score_elements(action_text, catalog)
        if confirmed_element:
            chosen = next((c for c in candidates if c["element_name"] == confirmed_element), None) or next(
                (c for c in catalog if c["element_name"] == confirmed_element), None
            )
            if chosen is None:
                trace.update({"outcome": "unmatched",
                              "detail": f"Confirmed element '{confirmed_element}' no longer on page"})
                return trace, None
        else:
            if not candidates:
                trace.update({"outcome": "unmatched", "detail": "No element on the current state matches this step"})
                return trace, None
            top = candidates[0]
            ambiguous = len(candidates) > 1 and candidates[1]["match_score"] == top["match_score"]
            if ambiguous and capture_mode == "assisted":
                trace.update({
                    "outcome": "needs_confirmation",
                    "detail": "Multiple elements match equally well — pick one to continue",
                    "candidates": [
                        {"element_name": c["element_name"], "role": c["role"],
                         "accessible_name": c["accessible_name"], "match_score": c["match_score"]}
                        for c in candidates[:5]
                    ],
                })
                return trace, None
            chosen = top

        if not chosen.get("ref"):
            trace.update({"outcome": "unmatched", "detail": f"Element '{chosen['element_name']}' has no live ref"})
            return trace, None

        label = chosen.get("accessible_name") or chosen["element_name"]
        if is_fill and chosen.get("role") in {"textbox", "searchbox", "combobox", "spinbutton"}:
            value = _data_value_for_step(action_text, test_data)
            if value is None:
                trace.update({"outcome": "unmatched",
                              "detail": "Data-entry step but no test_data value could be bound"})
                return trace, None
            await session.type_text(element=label, target=chosen["ref"], text=value)
            trace.update({"outcome": "filled", "element": chosen["element_name"]})
        else:
            await session.click(element=label, target=chosen["ref"])
            trace.update({"outcome": "clicked", "element": chosen["element_name"]})
        return trace, await session.snapshot()

    async def _package(
        self,
        session: MCPSession,
        parsed: ParsedSnapshot,
        raw: str,
        catalog: list[dict],
        *,
        sequence: int,
        produced_by_step: int | None,
        environment: str | None,
        output_dir,
    ) -> dict:
        """Build one Application State Evidence Package (data only — the
        service layer persists it). Snapshot text is masked HERE, before it
        ever leaves the agent."""
        masked = mask_snapshot_text(raw)
        screenshot_path: str | None = None
        try:
            # @playwright/mcp ignores --output-dir for browser_take_screenshot
            # and strips any directory component from `filename`, always
            # resolving the bare basename against the server subprocess's own
            # CWD (confirmed via two live runs: both a bare name and a full
            # absolute path landed at process-CWD/<basename>, which for this
            # worker is /app — the repo root bind mount). Passing a
            # collision-resistant unique name and moving the result into the
            # real workspace afterward is the only reliable way to land the
            # file where this evidence row claims it is, and avoids two
            # concurrent runs racing on the same CWD-relative filename.
            leak_name = f"grounded_poc_{uuid.uuid4().hex}.png"
            await session.call("browser_take_screenshot", {"filename": leak_name})
            leaked_path = Path.cwd() / leak_name
            if leaked_path.exists():
                target_path = output_dir / f"state_{sequence}.png"
                # Path.rename() raises EXDEV here — the CWD leak lands on the
                # ./backend bind mount while output_dir lives on the
                # stlc_storage named volume, different devices (confirmed
                # live: "OSError: Invalid cross-device link"). shutil.move
                # falls back to copy+delete across devices; plain rename
                # does not.
                shutil.move(str(leaked_path), str(target_path))
                screenshot_path = str(target_path)
            else:
                logger.warning(
                    "Screenshot for state %s not found at expected CWD-relative path %s",
                    sequence, leaked_path,
                )
        except Exception:
            logger.warning("Screenshot capture failed for state %s", sequence, exc_info=True)
        console: list[str] = []
        try:
            console_raw = await session.console_messages(level="error")
            console = [mask_snapshot_text(line) for line in console_raw.splitlines() if line.strip()][:20]
        except Exception:
            logger.debug("Console capture failed for state %s", sequence, exc_info=True)

        element_names = [e["element_name"] for e in catalog]
        return {
            "sequence": sequence,
            "state_fingerprint": state_fingerprint(parsed.page_url, parsed.page_title, element_names),
            "url": parsed.page_url,
            "title": parsed.page_title,
            "environment": environment,
            "elements": catalog,
            "snapshot_text": masked[:20000],
            "screenshot_path": screenshot_path,
            "blockers": _detect_live_blockers(masked),
            "console_evidence": console,
            "produced_by_step": produced_by_step,
        }

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            test_case=input_data.get("test_case") or {},
            application_url=input_data.get("application_url", ""),
            application_id=input_data.get("application_id"),
            environment=input_data.get("environment"),
            capture_mode=input_data.get("capture_mode", "automated"),
            routing=input_data.get("routing"),
            confirmed_actions=input_data.get("confirmed_actions"),
            max_steps=input_data.get("max_steps"),
            max_minutes=input_data.get("max_minutes"),
        )
        return result.data
