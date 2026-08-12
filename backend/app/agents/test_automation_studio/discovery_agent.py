"""Application discovery for the Test Automation Studio.

Opens the batch's application in a real, isolated, headless browser, signs in
if the batch carries credentials, and returns the interactive elements it
actually found — the evidence every locator downstream is grounded against.

Why this exists at all: Screens 1 and 2 read documents, and a document can
say "the user clicks Submit" without ever revealing that the real control is
a link labelled "Continue". Generating a script from prose alone therefore
produces locators that are fiction. This agent is the only place in the
studio that looks at the application instead of at text about it.

Deliberately built on the platform's existing browser layer rather than a new
one: `MCPSession` already owns the subprocess lifecycle, the navigation
allowlist, the audit hook and PII masking, and `parse_snapshot` already
converts the accessibility tree into structured elements. `_rank_elements` is
imported from the classic discovery agent for one specific reason — it is
what decides an element's `element_name`, and grounding matches a generated
contract element against that name. Two independent naming conventions would
silently un-ground every element.

Login is a heuristic, and is reported as one. The agent matches the field
labels the user supplied against the live accessibility tree; when the labels
are wrong, or the form is a custom widget with no accessible names, sign-in
fails and `auth_status="failed"` is returned with the reason. It never
guesses its way past a login it could not perform, because a crawl of the
login page reported as a crawl of the application is worse than no crawl.
"""
from __future__ import annotations

import logging
import uuid
from urllib.parse import urlparse

from app.agents.automation.mcp_discovery_agent import (
    _map_business_meanings,
    _rank_elements,
)
from app.agents.automation.mcp_session import (
    MCPSecurityError,
    MCPSession,
    MCPSessionConfig,
    mask_snapshot_text,
)
from app.agents.automation.snapshot_parser import ParsedSnapshot, parse_snapshot
from app.agents.base.base_agent import AgentRunResult, BaseAgent
from app.services.automation_runner.readiness import ReadinessInputs, check_readiness
from app.services.automation_runner.workspace import workspace_root

logger = logging.getLogger(__name__)

# How many extra pages one crawl may follow beyond the entry point. Bounded
# because this opens a real browser against someone's environment: a studio
# batch is not a licence to walk an entire application.
DEFAULT_MAX_PAGES = 6

# Words that identify a password field when the batch did not name one. Kept
# small and explicit — a wrong guess here types a password into a visible
# field, so anything ambiguous must fail rather than proceed.
_PASSWORD_HINTS = ("password", "passcode", "pin")
_SUBMIT_HINTS = ("sign in", "log in", "login", "signin", "submit", "continue", "next")

_TEXT_INPUT_ROLES = ("textbox", "searchbox", "combobox")


def _hosts_for(*urls: str | None) -> list[str]:
    hosts = []
    for url in urls:
        host = (urlparse(url).hostname or "") if url else ""
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _find_control(parsed: ParsedSnapshot, *, roles: tuple[str, ...], label: str | None, hints: tuple[str, ...] = ()):
    """The element whose accessible name best matches a label the user gave.

    Exact-ish match first (the label appears in the accessible name), then the
    built-in hints. Returns None rather than falling back to "the first one
    that happens to have the right role" when a label was explicitly supplied
    — a mis-targeted fill is how a password ends up typed into a search box.
    """
    candidates = [el for el in parsed.elements if el.role in roles and el.ref]
    if label:
        wanted = label.strip().lower()
        for el in candidates:
            if wanted and wanted in (el.name or "").lower():
                return el
        return None
    for hint in hints:
        for el in candidates:
            if hint in (el.name or "").lower():
                return el
    return None


def _looks_like_password_field(parsed: ParsedSnapshot) -> bool:
    return _find_control(parsed, roles=_TEXT_INPUT_ROLES, label=None, hints=_PASSWORD_HINTS) is not None


class TasDiscoveryAgent(BaseAgent):
    """Crawls one application and returns its real interactive elements."""

    name = "tas_application_discovery"

    async def run(
        self,
        *,
        application_url: str,
        auth_mode: str = "none",
        auth_config: dict | None = None,
        credentials: dict | None = None,
        relevance_text: str = "",
        max_pages: int = DEFAULT_MAX_PAGES,
    ) -> AgentRunResult:
        self._logs.clear()
        auth_config = auth_config or {}
        credentials = credentials or {}

        if not application_url:
            return AgentRunResult(
                success=False,
                error="This batch has no application URL, so there is nothing to discover.",
                data={},
                logs=self._logs,
            )

        self.log("info", "start", f"Discovering {application_url}")

        readiness = await check_readiness(
            ReadinessInputs(application_url=application_url, framework="playwright")
        )
        if not readiness.ready:
            blockers = [{"name": c.name, "detail": c.detail} for c in readiness.blockers]
            self.log("warning", "readiness", f"{len(blockers)} blocker(s)")
            return AgentRunResult(
                success=False,
                error=(
                    "The environment is not ready for discovery: "
                    + "; ".join(f"{b['name']}: {b['detail']}" for b in blockers)
                ),
                data={"blockers": blockers},
                logs=self._logs,
            )

        login_url = (auth_config.get("login_url") or "").strip() or None
        output_dir = workspace_root() / "tas_discovery" / uuid.uuid4().hex
        output_dir.mkdir(parents=True, exist_ok=True)
        config = MCPSessionConfig(
            allowed_hosts=_hosts_for(application_url, login_url),
            output_dir=str(output_dir),
        )

        async def audit(tool_name: str, arguments: dict, text: str) -> None:
            # Arguments are NOT logged: for browser_type they contain the
            # password. The masked result excerpt is enough for an audit trail.
            self.log(
                "info",
                "mcp_call",
                tool_name,
                data={"masked_result_excerpt": mask_snapshot_text(text)[:500]},
            )

        pages: list[dict] = []
        auth_status = "not_required"
        auth_detail: str | None = None

        try:
            async with MCPSession(config, on_call=audit) as session:
                if auth_mode == "form":
                    auth_status, auth_detail = await self._sign_in(
                        session,
                        login_url=login_url or application_url,
                        auth_config=auth_config,
                        credentials=credentials,
                    )
                    if auth_status == "failed":
                        # Still crawl: a catalog of the login page is honest
                        # evidence and tells the user what the labels really
                        # are, which is exactly what they need to fix it.
                        self.log("warning", "auth", auth_detail or "Sign-in failed")

                await session.navigate(application_url)
                raw = await session.snapshot()
                parsed = parse_snapshot(raw)
                pages.append(await self._page_record(parsed, application_url, relevance_text))

                for link in self._followable_links(parsed, relevance_text, max_pages - 1):
                    try:
                        await session.click(element=link.name or "link", target=link.ref or "")
                        follow_raw = await session.snapshot()
                    except Exception:
                        logger.warning(
                            "TAS discovery could not follow link %r", link.name, exc_info=True
                        )
                        continue
                    follow_parsed = parse_snapshot(follow_raw)
                    if any(p["url"] == (follow_parsed.page_url or "") for p in pages):
                        continue
                    pages.append(
                        await self._page_record(
                            follow_parsed, link.href or application_url, relevance_text
                        )
                    )
        except MCPSecurityError as exc:
            return AgentRunResult(
                success=False,
                error=f"Security policy blocked discovery: {exc}",
                data={},
                logs=self._logs,
            )
        except Exception as exc:
            logger.exception("TAS discovery failed for %s", application_url)
            return AgentRunResult(success=False, error=str(exc), data={}, logs=self._logs)

        element_count = sum(len(p["elements"]) for p in pages)
        self.log(
            "info",
            "complete",
            f"{element_count} element(s) across {len(pages)} page(s)",
        )
        return AgentRunResult(
            success=True,
            data={
                "pages": pages,
                "auth_status": auth_status,
                "auth_detail": auth_detail,
                "elements_discovered": element_count,
            },
            logs=self._logs,
        )

    async def _page_record(
        self, parsed: ParsedSnapshot, fallback_url: str, relevance_text: str
    ) -> dict:
        elements = _rank_elements(parsed)
        # Business meaning is what lets a step saying "confirm the order" match
        # a button named "Place order". Best-effort: a failure here leaves the
        # catalog usable, just harder to match by intent.
        meanings = await _map_business_meanings(
            elements, [{"title": relevance_text}] if relevance_text else []
        )
        for element in elements:
            if element["element_name"] in meanings:
                element["business_meaning"] = meanings[element["element_name"]]
        return {
            "url": parsed.page_url or fallback_url,
            "title": parsed.page_title,
            "elements": elements,
        }

    def _followable_links(self, parsed: ParsedSnapshot, relevance_text: str, limit: int):
        """In-app links whose name overlaps the test case text.

        Relevance-ordered rather than "the first N links" so a crawl bounded
        at six pages spends them on the flow the batch is about, not on the
        footer.
        """
        if limit <= 0:
            return []
        wanted = {w for w in (relevance_text or "").lower().split() if len(w) > 3}
        scored = []
        for el in parsed.elements:
            if el.role != "link" or not el.name or not el.ref:
                continue
            name_words = {w for w in el.name.lower().split() if len(w) > 3}
            overlap = len(wanted & name_words)
            if overlap:
                scored.append((overlap, el))
        scored.sort(key=lambda pair: -pair[0])
        return [el for _score, el in scored[:limit]]

    async def _sign_in(
        self, session: MCPSession, *, login_url: str, auth_config: dict, credentials: dict
    ) -> tuple[str, str | None]:
        """Fill and submit the login form. Returns (auth_status, detail)."""
        username = credentials.get("username") or ""
        password = credentials.get("password") or ""
        if not username or not password:
            return "skipped", "No credentials are stored for this batch."

        await session.navigate(login_url)
        parsed = parse_snapshot(await session.snapshot())

        username_field = _find_control(
            parsed,
            roles=_TEXT_INPUT_ROLES,
            label=auth_config.get("username_label"),
            hints=("username", "user name", "email", "user id", "login"),
        )
        password_field = _find_control(
            parsed,
            roles=_TEXT_INPUT_ROLES,
            label=auth_config.get("password_label"),
            hints=_PASSWORD_HINTS,
        )
        if username_field is None or password_field is None:
            visible = ", ".join(
                f'{el.role} "{el.name}"'
                for el in parsed.elements
                if el.role in _TEXT_INPUT_ROLES and el.name
            )
            return "failed", (
                "Could not find the username and password fields on the sign-in page. "
                f"Text inputs found were: {visible or 'none'}. "
                "Set the field labels on the batch to match."
            )

        submit = _find_control(
            parsed, roles=("button",), label=auth_config.get("submit_label"), hints=_SUBMIT_HINTS
        )

        await session.type_text(
            element=username_field.name or "username", target=username_field.ref or "", text=username
        )
        await session.type_text(
            element=password_field.name or "password",
            target=password_field.ref or "",
            text=password,
            # Submitting from the password field covers forms whose submit
            # control has no accessible name at all.
            submit=submit is None,
        )
        if submit is not None:
            await session.click(element=submit.name or "submit", target=submit.ref or "")

        after = parse_snapshot(await session.snapshot())
        if _looks_like_password_field(after):
            # A password field still on screen after submitting is the most
            # reliable signal available from an accessibility tree that the
            # credentials were rejected. It is a heuristic, and it is reported
            # as the reason rather than as a certainty.
            return "failed", (
                "A password field is still present after submitting, so sign-in appears to have "
                "been rejected. Check the stored credentials and the field labels."
            )
        return "succeeded", f"Signed in as {username[:2]}***"

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(
            application_url=input_data.get("application_url", ""),
            auth_mode=input_data.get("auth_mode", "none"),
            auth_config=input_data.get("auth_config"),
            credentials=input_data.get("credentials"),
            relevance_text=input_data.get("relevance_text", ""),
            max_pages=input_data.get("max_pages", DEFAULT_MAX_PAGES),
        )
        if not result.success:
            raise ValueError(result.error or "Discovery failed")
        return result.data
