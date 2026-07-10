"""
Playwright MCP session manager (Phase 3, ADR-001 / Phase-3 plan §3.1, §3.7).

Wraps the `mcp` Python SDK's stdio client against a pinned `@playwright/mcp`
Node process (invoked via `npx`). One isolated headless session per agent
run — the process is spawned fresh and torn down at the end of every
discovery run, never shared or reused across runs or projects.

Security controls (§3.7), enforced here rather than left to the subprocess
flags alone (the server's own --allowed-origins/--blocked-origins docs
explicitly say "does not serve as a security boundary and does not affect
redirects"):
  - Navigation allowlist is checked in Python BEFORE every browser_navigate
    call — that check, not the CLI flag, is the actual boundary. The CLI
    flag is still passed too, as defense in depth.
  - No file-upload / drag-drop / clipboard wrapper methods exist on this
    class — omission, not configuration, is what keeps them unreachable.
    Clipboard permissions are never granted (no --grant-permissions passed).
  - Credentials never appear in a prompt or tool argument — they reach the
    browser only via --storage-state / --secrets file paths, whose contents
    this module never reads or logs.
  - Every tool call is routed through `call()`, which invokes the caller's
    `on_call` audit hook (the discovery agent wires this to AgentLog) before
    returning — a call this module doesn't know about can't happen, and a
    call that happens can't skip the audit trail.
  - PII masking of returned content (`mask_snapshot_text`) is separate from
    the transport on purpose: callers must explicitly mask before
    persisting, so masking can't be silently skipped by a transport-level
    default that later changes.

This module never decides whether the tested page's content is trustworthy —
callers (the discovery agent) must always treat returned snapshot/console
text as `<user_content>` data when it reaches an LLM prompt, never as
instructions.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable
from urllib.parse import urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)

# Pinned per ADR-001 — bump deliberately (test the new version first), never
# track @latest. Node/npx and a pre-installed Chromium are assumed present
# (same runtime the automation_runner already requires).
PLAYWRIGHT_MCP_PACKAGE = "@playwright/mcp@0.0.77"

_chromium_executable_path_cache: str | None | bool = False  # False = not yet resolved


def _resolve_chromium_executable_path() -> str | None:
    """Find the Chromium binary `playwright install` already provisioned.

    This pinned @playwright/mcp version's --browser flag only accepts
    chrome|firefox|webkit|msedge — no "chromium" value — so it defaults to
    the "chrome" channel, which requires a real Google Chrome install
    nothing here provisions (confirmed via a live run: "Chromium
    distribution 'chrome' is not found at /opt/google/chrome/chrome").
    --executable-path sidesteps the channel entirely by pointing straight at
    the Chromium build Playwright already installed.

    Deliberately a plain filesystem glob, not `playwright.sync_api` /
    `async_api` — `sync_playwright()` raises "It looks like you are using
    Playwright Sync API inside the asyncio loop" when called from this
    module's actual caller (an async Celery task), and juggling the async
    API's own driver lifecycle here just to read one path isn't worth the
    fragility. The install layout (`<cache>/chromium-<build>/chrome-linux/
    chrome`) is stable across Playwright versions; only the build number
    changes, which the glob handles.
    """
    global _chromium_executable_path_cache
    if _chromium_executable_path_cache is not False:
        return _chromium_executable_path_cache
    try:
        cache_dir = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH") or (Path.home() / ".cache" / "ms-playwright"))
        candidates = sorted(
            cache_dir.glob("chromium-*/chrome-linux/chrome"),
            key=lambda p: p.parent.parent.name,
            reverse=True,  # highest build number (most recently installed) first
        )
        _chromium_executable_path_cache = str(candidates[0]) if candidates else None
    except OSError:
        logger.warning("Could not resolve a local Chromium executable path", exc_info=True)
        _chromium_executable_path_cache = None
    return _chromium_executable_path_cache

OnCall = Callable[[str, dict[str, Any], str], Awaitable[None]]
"""on_call(tool_name, arguments, result_text_excerpt) -> None"""


class MCPSecurityError(RuntimeError):
    """Raised when the agent attempts an action outside its security policy
    (e.g. navigating off the configured allowlist)."""


@dataclass
class MCPSessionConfig:
    allowed_hosts: list[str] = field(default_factory=list)
    """Hostnames (not full URLs) the session may navigate to — derived from
    the project's configured Applications & Environments, never free-form
    or LLM-supplied."""
    storage_state_path: str | None = None
    secrets_path: str | None = None
    headless: bool = True
    timeout_action_ms: int = 10_000
    timeout_navigation_ms: int = 30_000
    viewport: str | None = None
    # Where the server writes snapshot/console-log files it doesn't inline
    # (see mcp_discovery_agent's note on browser_navigate vs browser_snapshot).
    # Without this, it defaults to a .playwright-mcp/ dir under the
    # process's CWD — fine for local smoke-testing, not for a worker
    # process. Callers should pass a per-run workspace path.
    output_dir: str | None = None


def _host_allowed(url: str, allowed_hosts: list[str]) -> bool:
    if not allowed_hosts:
        return False
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    return any(host == h.lower() or host.endswith("." + h.lower()) for h in allowed_hosts)


class MCPSession:
    """Async context manager around one @playwright/mcp stdio subprocess.

    Usage:
        async with MCPSession(config, on_call=audit) as session:
            await session.navigate("https://app.example.com/login")
            snapshot = await session.snapshot()
    """

    def __init__(self, config: MCPSessionConfig, *, on_call: OnCall | None = None):
        self._config = config
        self._on_call = on_call
        self._session: ClientSession | None = None
        self._stdio_cm = None
        self._session_cm = None

    def _build_args(self) -> list[str]:
        args = ["-y", PLAYWRIGHT_MCP_PACKAGE, "--isolated", "--no-sandbox"]
        chromium_path = _resolve_chromium_executable_path()
        if chromium_path:
            # --executable-path only overrides *where* the selected --browser
            # channel's binary lives — without an explicit --browser it's
            # silently ignored and the server still probes for a real Google
            # Chrome install (confirmed via a live run). --browser chrome
            # plus --executable-path together point the "chrome" channel at
            # the Chromium build Playwright already provisioned.
            args += ["--browser", "chrome", "--executable-path", chromium_path]
        if self._config.headless:
            args.append("--headless")
        args += ["--timeout-action", str(self._config.timeout_action_ms)]
        args += ["--timeout-navigation", str(self._config.timeout_navigation_ms)]
        if self._config.viewport:
            args += ["--viewport-size", self._config.viewport]
        if self._config.storage_state_path:
            args += ["--storage-state", self._config.storage_state_path]
        if self._config.secrets_path:
            args += ["--secrets", self._config.secrets_path]
        if self._config.output_dir:
            args += ["--output-dir", self._config.output_dir]
        # Deliberately NOT passing --allowed-origins here: it requires exact
        # scheme://host:port origins (a bare hostname silently mismatches
        # and blocks legitimate navigation — confirmed while building this),
        # and the server's own docs say it "does not serve as a security
        # boundary" anyway. _host_allowed() in navigate() below is the real,
        # single boundary — simpler and not fooled by a format mismatch.
        return args

    async def __aenter__(self) -> "MCPSession":
        params = StdioServerParameters(command="npx", args=self._build_args())
        self._stdio_cm = stdio_client(params)
        read, write = await self._stdio_cm.__aenter__()
        self._session_cm = ClientSession(read, write)
        self._session = await self._session_cm.__aenter__()
        await self._session.initialize()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            if self._session is not None:
                await self.call("browser_close", {})
        except Exception:
            logger.warning("browser_close failed during MCP session teardown", exc_info=True)
        try:
            if self._session_cm is not None:
                await self._session_cm.__aexit__(exc_type, exc, tb)
        finally:
            if self._stdio_cm is not None:
                await self._stdio_cm.__aexit__(exc_type, exc, tb)

    async def call(self, tool_name: str, arguments: dict[str, Any]) -> str:
        """Invoke an MCP tool and route the result through the audit hook.
        The only path through which any tool call happens — every wrapper
        method below goes through this."""
        assert self._session is not None, "MCPSession used outside its `async with` block"
        result = await self._session.call_tool(tool_name, arguments)
        text = "\n".join(getattr(c, "text", "") or "" for c in result.content)
        if self._on_call:
            await self._on_call(tool_name, arguments, text[:4000])
        if result.isError:
            raise RuntimeError(f"MCP tool '{tool_name}' returned an error: {text[:500]}")
        return text

    async def navigate(self, url: str) -> str:
        if not _host_allowed(url, self._config.allowed_hosts):
            raise MCPSecurityError(
                f"Navigation to '{url}' is outside the allowed hosts {self._config.allowed_hosts}"
            )
        return await self.call("browser_navigate", {"url": url})

    async def snapshot(self) -> str:
        return await self.call("browser_snapshot", {})

    async def click(self, *, element: str, target: str) -> str:
        return await self.call("browser_click", {"element": element, "target": target})

    async def type_text(self, *, element: str, target: str, text: str, submit: bool = False) -> str:
        return await self.call(
            "browser_type", {"element": element, "target": target, "text": text, "submit": submit}
        )

    async def fill_form(self, fields: list[dict[str, Any]]) -> str:
        return await self.call("browser_fill_form", {"fields": fields})

    async def console_messages(self, *, level: str = "info") -> str:
        return await self.call("browser_console_messages", {"level": level})


_PII_PATTERNS = [
    re.compile(r"[\w.+-]+@[\w-]+\.[A-Za-z]{2,}"),  # email
    re.compile(r"\+?\d[\d\s\-()]{7,}\d"),  # phone-ish
    re.compile(r"\b\d{4}[ -]?\d{4}[ -]?\d{4}[ -]?\d{4}\b"),  # card-like
]


def mask_snapshot_text(text: str) -> str:
    """Redact obvious PII from a snapshot/console excerpt before it is
    persisted (AgentLog, locator_map, evidence). Best-effort regex masking,
    not a DLP replacement — a real DLP scan is documented follow-up work in
    the plan (Phase 3.7)."""
    masked = text
    for pattern in _PII_PATTERNS:
        masked = pattern.sub("[REDACTED]", masked)
    return masked
