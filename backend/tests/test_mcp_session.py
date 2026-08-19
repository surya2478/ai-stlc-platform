"""Phase 3.7 security tests for the MCP session wrapper. Never spawns a real
subprocess — the security boundary (_host_allowed) is checked in Python
before any tool call would be dispatched, so it's testable without a live
browser."""
import anyio
import pytest

from app.agents.automation import mcp_session
from app.agents.automation.mcp_session import (
    MCPSecurityError,
    MCPSession,
    MCPSessionConfig,
    _host_allowed,
    mask_snapshot_text,
)


def test_host_allowed_matches_exact_and_subdomain():
    assert _host_allowed("https://app.example.com/login", ["app.example.com"]) is True
    assert _host_allowed("https://staging.app.example.com/login", ["app.example.com"]) is True
    assert _host_allowed("https://evil.com/", ["app.example.com"]) is False


def test_host_allowed_rejects_lookalike_domain():
    # "app.example.com.evil.com" must NOT match "app.example.com" — only an
    # exact host or a true subdomain (suffix after a dot) is allowed.
    assert _host_allowed("https://app.example.com.evil.com/", ["app.example.com"]) is False


def test_host_allowed_false_with_no_configured_hosts():
    assert _host_allowed("https://anything.com/", []) is False


def test_navigate_blocks_off_allowlist_url_without_spawning_a_subprocess():
    config = MCPSessionConfig(allowed_hosts=["app.example.com"])
    session = MCPSession(config)
    # Deliberately not entering the `async with` block / not setting
    # self._session — proves the allowlist check happens before any attempt
    # to use the (nonexistent) transport.
    async def run():
        with pytest.raises(MCPSecurityError):
            await session.navigate("https://evil.example.com/steal-data")
    anyio.run(run)


def test_session_exposes_no_file_upload_or_clipboard_methods():
    # Omission is the control: these wrapper methods must not exist at all.
    for forbidden in ("file_upload", "upload_file", "drop", "drag", "clipboard"):
        assert not hasattr(MCPSession, forbidden), f"MCPSession must not expose {forbidden}()"


def test_build_args_never_includes_allowed_origins_flag():
    # --allowed-origins requires exact scheme://host:port and silently
    # blocks legitimate navigation on a mismatch (confirmed against a live
    # server) — the real boundary is _host_allowed(), not this CLI flag.
    config = MCPSessionConfig(allowed_hosts=["app.example.com"])
    session = MCPSession(config)
    args = session._build_args()
    assert not any("allowed-origins" in a for a in args)
    assert "--isolated" in args
    assert "--no-sandbox" in args


def test_build_args_pins_chromium_executable_when_resolvable(monkeypatch):
    # This pinned @playwright/mcp version's --browser flag only accepts
    # chrome|firefox|webkit|msedge (no "chromium"), so it defaults to the
    # "chrome" channel — which nothing here provisions. A live run failed
    # with "Chromium distribution 'chrome' is not found at
    # /opt/google/chrome/chrome". --executable-path only overrides where a
    # channel's binary lives when --browser is also set explicitly
    # (confirmed live — without it, --executable-path alone is silently
    # ignored) — so both flags together point the "chrome" channel at the
    # Chromium build Playwright already installed, resolved dynamically
    # rather than hardcoded.
    monkeypatch.setattr(mcp_session, "_resolve_chromium_executable_path", lambda: "/fake/chrome-linux/chrome")
    config = MCPSessionConfig(allowed_hosts=["app.example.com"])
    session = MCPSession(config)
    args = session._build_args()
    browser_idx = args.index("--browser")
    assert args[browser_idx + 1] == "chrome"
    path_idx = args.index("--executable-path")
    assert args[path_idx + 1] == "/fake/chrome-linux/chrome"


def test_build_args_omits_executable_path_when_unresolvable(monkeypatch):
    monkeypatch.setattr(mcp_session, "_resolve_chromium_executable_path", lambda: None)
    config = MCPSessionConfig(allowed_hosts=["app.example.com"])
    session = MCPSession(config)
    args = session._build_args()
    assert "--executable-path" not in args


def test_build_args_includes_storage_state_and_secrets_paths_not_raw_credentials():
    config = MCPSessionConfig(
        allowed_hosts=["app.example.com"],
        storage_state_path="/secrets/storage_state.json",
        secrets_path="/secrets/creds.env",
    )
    session = MCPSession(config)
    args = session._build_args()
    assert "--storage-state" in args
    assert "/secrets/storage_state.json" in args
    assert "--secrets" in args
    assert "/secrets/creds.env" in args


def test_mask_snapshot_text_redacts_email_phone_and_card_like_values():
    text = "Contact jane.doe@example.com or call +1 555-123-4567. Card 4111 1111 1111 1111 on file."
    masked = mask_snapshot_text(text)
    assert "jane.doe@example.com" not in masked
    assert "555-123-4567" not in masked
    assert "4111 1111 1111 1111" not in masked
    assert "[REDACTED]" in masked


def test_call_routes_through_audit_hook_and_is_the_only_call_path():
    """Every wrapper method (navigate/snapshot/click/...) must go through
    `call()` so the audit hook can't be bypassed — verified by checking they
    all call self.call internally rather than the raw session directly."""
    import inspect

    from app.agents.automation import mcp_session as mod

    src = inspect.getsource(mod.MCPSession)
    for method in ("navigate", "snapshot", "click", "type_text", "fill_form", "console_messages"):
        # crude but effective: each method's body must reference `self.call(`
        method_src = src.split(f"async def {method}(")[1].split("\n\n")[0]
        assert "self.call(" in method_src, f"{method} must dispatch through self.call()"


# --- server launch command (air-gap): the discovery run must not need npm ---


@pytest.fixture
def _clear_server_command_cache(monkeypatch):
    """resolve_server_command() memoises per process; each case needs a fresh
    resolution."""
    monkeypatch.setattr(mcp_session, "_server_command_cache", None)


def test_resolve_server_command_uses_installed_binary_without_npx(
    monkeypatch, _clear_server_command_cache
):
    # The whole point: a container with no registry access must still start
    # the server. `npx -y @playwright/mcp@<version>` is a package spec, so npm
    # resolves it through its install path and reaches the network.
    monkeypatch.setattr(mcp_session.shutil, "which", lambda name: "/usr/bin/playwright-mcp")
    monkeypatch.setattr(
        mcp_session, "_installed_mcp_version", lambda _b: mcp_session.PLAYWRIGHT_MCP_VERSION
    )
    command, launch_args = mcp_session.resolve_server_command()
    assert command == "/usr/bin/playwright-mcp"
    assert launch_args == []


def test_session_spawn_args_carry_no_package_spec_when_binary_installed(
    monkeypatch, _clear_server_command_cache
):
    monkeypatch.setattr(mcp_session.shutil, "which", lambda name: "/usr/bin/playwright-mcp")
    monkeypatch.setattr(
        mcp_session, "_installed_mcp_version", lambda _b: mcp_session.PLAYWRIGHT_MCP_VERSION
    )
    command, launch_args = mcp_session.resolve_server_command()
    session = MCPSession(MCPSessionConfig(allowed_hosts=["app.example.com"]))
    full = launch_args + session._build_args()
    assert command != "npx"
    assert not any(a.startswith("@playwright/mcp") for a in full)
    assert "-y" not in full


def test_resolve_server_command_falls_back_to_npx_when_binary_missing(
    monkeypatch, _clear_server_command_cache
):
    # Bare-metal checkouts that never ran the image build still work
    # (backend/AUTOMATION_RUNNER.md documents that setup).
    monkeypatch.setattr(mcp_session.shutil, "which", lambda name: None)
    command, launch_args = mcp_session.resolve_server_command()
    assert command == "npx"
    assert launch_args == ["-y", mcp_session.PLAYWRIGHT_MCP_PACKAGE]


def test_resolve_server_command_rejects_a_version_other_than_the_pin(
    monkeypatch, _clear_server_command_cache
):
    # ADR-001 pins this server; driving an untested build silently is exactly
    # what the pin exists to prevent, so a mismatch falls back rather than
    # being used.
    monkeypatch.setattr(mcp_session.shutil, "which", lambda name: "/usr/bin/playwright-mcp")
    monkeypatch.setattr(mcp_session, "_installed_mcp_version", lambda _b: "0.0.1")
    command, _ = mcp_session.resolve_server_command()
    assert command == "npx"


def test_resolve_server_command_uses_binary_when_version_unreadable(
    monkeypatch, _clear_server_command_cache
):
    # Failing closed here would reintroduce the network fetch this exists to
    # remove, so an unreadable version is not treated as a mismatch.
    monkeypatch.setattr(mcp_session.shutil, "which", lambda name: "/usr/bin/playwright-mcp")
    monkeypatch.setattr(mcp_session, "_installed_mcp_version", lambda _b: None)
    command, _ = mcp_session.resolve_server_command()
    assert command == "/usr/bin/playwright-mcp"
