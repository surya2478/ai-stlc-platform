import anyio

from app.agents.automation import mcp_discovery_agent as mod
from app.agents.automation.mcp_discovery_agent import (
    PlaywrightMCPDiscoveryAgent,
    _detect_live_blockers,
    _rank_elements,
    _relevant_links,
)
from app.agents.automation.snapshot_parser import parse_snapshot
from app.services.automation_runner.readiness import ReadinessCheck, ReadinessResult

LOGIN_SNAPSHOT = """### Page
- Page URL: http://app.example.com/login
- Page Title: Sign in
### Snapshot
```yaml
- generic [ref=e1]:
  - textbox "Username" [ref=e2]
  - button "Sign in" [ref=e3]
  - link "Help center" [ref=e4]:
    - /url: /help
```
"""

HELP_SNAPSHOT = """### Page
- Page URL: http://app.example.com/help
- Page Title: Help
### Snapshot
```yaml
- generic [ref=e1]:
  - heading "Help center" [level=1] [ref=e2]
```
"""

OTP_SNAPSHOT = """### Page
- Page URL: http://app.example.com/verify
- Page Title: Verify
### Snapshot
```yaml
- generic [ref=e1]:
  - text: Enter the OTP sent to your phone
  - textbox "OTP code" [ref=e2]
```
"""


def test_rank_elements_prefers_role_strategy_with_high_confidence_when_named():
    parsed = parse_snapshot(LOGIN_SNAPSHOT)
    ranked = _rank_elements(parsed)
    username = next(e for e in ranked if e["accessible_name"] == "Username")
    assert username["recommended_strategy"] == "role"
    assert username["confidence_score"] == 90
    assert "getByRole" in username["recommended_locator"]


def test_rank_elements_lower_confidence_without_accessible_name():
    from app.agents.automation.snapshot_parser import SnapshotElement
    parsed = parse_snapshot(LOGIN_SNAPSHOT)
    parsed.elements.append(SnapshotElement(role="button", name=None, ref="e9", depth=1))
    ranked = _rank_elements(parsed)
    unnamed = next(e for e in ranked if e["element_name"] == "button_unnamed")
    assert unnamed["confidence_score"] < 90


# ── Duplicate accessible-name disambiguation ─────────────────────────────────
# A live run failed with a Playwright "strict mode violation": two "Show
# password" icon buttons (one next to Password, one next to Confirm
# Password) collapsed to the SAME element_name, and the surviving
# getByRole(role, {name}) locator matched both real elements at runtime.

SIGNUP_SNAPSHOT_WITH_DUPLICATE_BUTTONS = """### Page
- Page URL: http://app.example.com/sign-up
- Page Title: Sign up
### Snapshot
```yaml
- generic [ref=e1]:
  - textbox "Password" [ref=e2]
  - button "Show password" [ref=e3]
  - textbox "Confirm password" [ref=e4]
  - button "Show password" [ref=e5]
  - button "Create account" [ref=e6]
```
"""


def test_rank_elements_disambiguates_duplicate_accessible_names():
    parsed = parse_snapshot(SIGNUP_SNAPSHOT_WITH_DUPLICATE_BUTTONS)
    ranked = _rank_elements(parsed)
    show_password_entries = [e for e in ranked if e["accessible_name"] == "Show password"]
    assert len(show_password_entries) == 2

    names = {e["element_name"] for e in show_password_entries}
    assert names == {"button_show_password", "button_show_password_2"}

    first = next(e for e in show_password_entries if e["element_name"] == "button_show_password")
    second = next(e for e in show_password_entries if e["element_name"] == "button_show_password_2")
    assert first["recommended_locator"] == (
        "page.getByRole('button', { name: 'Show password', exact: true }).nth(0)"
    )
    assert second["recommended_locator"] == (
        "page.getByRole('button', { name: 'Show password', exact: true }).nth(1)"
    )


def test_rank_elements_does_not_disambiguate_unique_names():
    """Elements that already have a unique (role, name) pair on the page
    must be left completely unchanged — no .nth() suffix, no renamed key."""
    parsed = parse_snapshot(SIGNUP_SNAPSHOT_WITH_DUPLICATE_BUTTONS)
    ranked = _rank_elements(parsed)
    create_account = next(e for e in ranked if e["accessible_name"] == "Create account")
    assert create_account["element_name"] == "button_create_account"
    assert ".nth(" not in create_account["recommended_locator"]


def test_relevant_links_matches_on_keyword_overlap():
    parsed = parse_snapshot(LOGIN_SNAPSHOT)
    test_cases = [{"title": "User visits help center", "steps": []}]
    links = _relevant_links(parsed, test_cases)
    assert len(links) == 1
    assert links[0].name == "Help center"


def test_relevant_links_empty_when_no_overlap():
    parsed = parse_snapshot(LOGIN_SNAPSHOT)
    test_cases = [{"title": "Completely unrelated flow about billing invoices", "steps": []}]
    links = _relevant_links(parsed, test_cases)
    assert links == []


def test_detect_live_blockers_finds_otp_mention():
    reasons = _detect_live_blockers(OTP_SNAPSHOT)
    assert any("OTP" in r for r in reasons)


def test_detect_live_blockers_empty_for_clean_page():
    reasons = _detect_live_blockers(LOGIN_SNAPSHOT)
    assert reasons == []


class _FakeMCPSession:
    """Stands in for mcp_session.MCPSession — queues canned snapshot
    responses instead of spawning a real browser subprocess."""
    instances = []

    def __init__(self, config, on_call=None):
        self.config = config
        self.on_call = on_call
        self.navigate_calls = []
        self.click_calls = []
        self._snapshots = list(_FakeMCPSession.queued_snapshots)
        _FakeMCPSession.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return False

    async def navigate(self, url):
        self.navigate_calls.append(url)
        return ""

    async def snapshot(self):
        return self._snapshots.pop(0)

    async def click(self, *, element, target):
        self.click_calls.append((element, target))


async def _no_op_business_meanings(*_a, **_k):
    return {}


def _patch_ready(monkeypatch, ready=True):
    async def fake_check_readiness(_inputs):
        if ready:
            return ReadinessResult(checks=[ReadinessCheck("application_url_reachable", True, "ok")])
        return ReadinessResult(checks=[ReadinessCheck("application_url_reachable", False, "unreachable")])
    monkeypatch.setattr(mod, "check_readiness", fake_check_readiness)


def test_discover_application_builds_locator_data_and_follows_relevant_link(monkeypatch):
    _patch_ready(monkeypatch, ready=True)
    monkeypatch.setattr(mod, "_map_business_meanings", _no_op_business_meanings)
    _FakeMCPSession.queued_snapshots = [LOGIN_SNAPSHOT, HELP_SNAPSHOT]
    _FakeMCPSession.instances = []
    monkeypatch.setattr(mod, "MCPSession", _FakeMCPSession)

    agent = PlaywrightMCPDiscoveryAgent()
    test_cases = [{"id": 1, "test_case_id": "TC-1", "title": "User visits help center", "steps": []}]

    async def run():
        return await agent._discover_application(7, "http://app.example.com/login", test_cases)

    result = anyio.run(run)

    assert result["application_id"] == 7
    assert len(result["pages"]) == 2  # login page + followed "Help center" link
    login_page = result["pages"][0]
    element_names = {el["element_name"] for el in login_page["elements"]}
    assert "textbox_username" in element_names
    assert "button_sign_in" in element_names
    assert "link_help_center" in element_names


def test_discover_application_detects_live_eligibility_blocker(monkeypatch):
    _patch_ready(monkeypatch, ready=True)
    monkeypatch.setattr(mod, "_map_business_meanings", _no_op_business_meanings)
    _FakeMCPSession.queued_snapshots = [OTP_SNAPSHOT]
    _FakeMCPSession.instances = []
    monkeypatch.setattr(mod, "MCPSession", _FakeMCPSession)

    agent = PlaywrightMCPDiscoveryAgent()
    test_cases = [{"id": 1, "test_case_id": "TC-1", "title": "Verify OTP", "steps": []}]

    async def run():
        return await agent._discover_application(7, "http://app.example.com/verify", test_cases)

    result = anyio.run(run)
    assert "TC-1" in result["eligibility_overrides"]
    assert any("OTP" in r for r in result["eligibility_overrides"]["TC-1"])


def test_run_skips_application_when_readiness_not_ready(monkeypatch):
    _patch_ready(monkeypatch, ready=False)
    monkeypatch.setattr(mod, "_map_business_meanings", _no_op_business_meanings)

    agent = PlaywrightMCPDiscoveryAgent()

    async def run():
        return await agent.run(test_cases=[{
            "id": 1, "test_case_id": "TC-1", "title": "x", "steps": [],
            "application_id": 7, "application_url": "http://app.example.com/login",
        }])

    result = anyio.run(run)
    assert result.success is False
    assert "not ready" in result.error.lower() or "not ready" in " ".join(
        log["message"] for log in result.logs
    ).lower()


def test_run_reports_error_when_no_application_url_resolved(monkeypatch):
    agent = PlaywrightMCPDiscoveryAgent()

    async def run():
        return await agent.run(test_cases=[{
            "id": 1, "test_case_id": "TC-1", "title": "x", "steps": [],
            "application_id": 7, "application_url": None,
        }])

    result = anyio.run(run)
    assert result.success is False


def test_run_fails_cleanly_with_no_test_cases():
    agent = PlaywrightMCPDiscoveryAgent()

    async def run():
        return await agent.run(test_cases=[])

    result = anyio.run(run)
    assert result.success is False
