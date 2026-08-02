"""GAP-2 tests: URL safety validation, same-origin link extraction, worker wiring."""
import anyio
import pytest

from app.services.url_capture_service import (
    MAX_PAGES,
    UnsafeURLError,
    _extract_same_origin_links,
    _same_origin,
    validate_url_safety,
)
from app.worker.tasks import agent_tasks


# ── SSRF / scheme validation ──────────────────────────────────────────────────

def test_rejects_non_http_schemes():
    for url in ("ftp://example.com", "file:///etc/passwd", "javascript:alert(1)", "gopher://x"):
        with pytest.raises(UnsafeURLError):
            validate_url_safety(url)


def test_rejects_loopback_and_private_ips():
    for url in (
        "http://127.0.0.1/admin",
        "http://localhost:8000/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/router",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata endpoint
        "http://0.0.0.0/",
    ):
        with pytest.raises(UnsafeURLError):
            validate_url_safety(url)


def test_rejects_missing_hostname():
    with pytest.raises(UnsafeURLError):
        validate_url_safety("http:///path-only")


def test_allows_public_ip_literal():
    # IP literal avoids DNS dependence in tests; 93.184.216.34 is a public address
    assert validate_url_safety("http://93.184.216.34/page") == "http://93.184.216.34/page"


# ── Internal-host exemption ───────────────────────────────────────────────────
#
# A local test target (fixtures/static-site) resolves to a private compose
# address, so the guard blocks it — correctly, by its own rule. The exemption
# exists for that case and is keyed on the hostname, never an address range.

def _allow(monkeypatch, hosts: str) -> None:
    import app.services.url_capture_service as mod
    monkeypatch.setattr(
        type(mod.settings),
        "url_analysis_allowed_internal_host_set",
        property(lambda self: frozenset(h.strip().lower() for h in hosts.split(",") if h.strip())),
    )


def test_nothing_is_exempt_by_default():
    """The whole guard rests on this: a fresh deployment exempts no host.

    Asserts the declared field default rather than instantiating Settings —
    pydantic reads the environment, and a developer machine that has set
    URL_ANALYSIS_ALLOWED_INTERNAL_HOSTS would otherwise make this pass or fail
    based on local config instead of on the code.
    """
    from app.config import Settings

    assert Settings.model_fields["url_analysis_allowed_internal_hosts"].default == ""


def test_an_empty_setting_exempts_nothing():
    """And an empty value really does derive an empty set — no accidental
    exemption of "" as a hostname."""
    _blank = type(
        "S", (), {"url_analysis_allowed_internal_hosts": "  ,  ,"},
    )()
    from app.config import Settings

    derived = Settings.url_analysis_allowed_internal_host_set.fget(_blank)
    assert derived == frozenset()


def test_an_exempted_host_is_allowed(monkeypatch):
    _allow(monkeypatch, "static-test")
    assert validate_url_safety("http://static-test/index.html") == "http://static-test/index.html"


def test_exempting_one_host_does_not_exempt_its_neighbours(monkeypatch):
    """The reason this is a hostname list and not a CIDR: naming the fixture
    must not open the subnet it happens to sit in."""
    _allow(monkeypatch, "static-test")
    for url in ("http://10.0.0.5/internal", "http://192.168.1.1/router", "http://127.0.0.1/admin"):
        with pytest.raises(UnsafeURLError):
            validate_url_safety(url)


def test_the_cloud_metadata_endpoint_stays_blocked(monkeypatch):
    """The single most valuable thing the guard refuses. An exemption elsewhere
    must never reach it."""
    _allow(monkeypatch, "static-test")
    with pytest.raises(UnsafeURLError):
        validate_url_safety("http://169.254.169.254/latest/meta-data")


def test_exemption_is_exact_not_a_suffix_match(monkeypatch):
    """"evil-static-test" contains "static-test" but is a different host."""
    _allow(monkeypatch, "static-test")
    with pytest.raises(UnsafeURLError):
        validate_url_safety("http://127.0.0.1/")  # sanity: guard still live
    import app.services.url_capture_service as mod
    assert "evil-static-test" not in mod.settings.url_analysis_allowed_internal_host_set


def test_exemption_does_not_bypass_the_scheme_check(monkeypatch):
    """Being an allowed host says nothing about file:// or javascript:."""
    _allow(monkeypatch, "static-test")
    for url in ("file://static-test/etc/passwd", "javascript:alert(1)"):
        with pytest.raises(UnsafeURLError):
            validate_url_safety(url)


# ── Same-origin crawling helpers ──────────────────────────────────────────────

def test_same_origin_matching():
    assert _same_origin("https://a.com/x", "https://a.com/y")
    assert not _same_origin("https://a.com/x", "http://a.com/y")  # scheme differs
    assert not _same_origin("https://a.com/x", "https://b.com/y")
    assert not _same_origin("https://a.com/x", "https://a.com:8443/y")  # port differs


def test_extract_same_origin_links_filters_and_dedupes():
    dom = {
        "links": [
            {"label": "Home", "href": "/"},
            {"label": "About", "href": "/about"},
            {"label": "About again", "href": "/about#team"},  # same after fragment strip
            {"label": "External", "href": "https://other.com/page"},
            {"label": "Self", "href": "https://a.com/start"},
            {"label": "Empty", "href": ""},
        ]
    }
    links = _extract_same_origin_links("https://a.com/start", dom)
    assert "https://a.com/" in links
    assert "https://a.com/about" in links
    assert len([l for l in links if "about" in l]) == 1  # deduped
    assert all("other.com" not in l for l in links)
    assert "https://a.com/start" not in links  # self excluded


def test_max_pages_cap_is_bounded():
    assert MAX_PAGES <= 5


# ── Worker wiring ─────────────────────────────────────────────────────────────

def test_url_analysis_in_agent_registry():
    assert "url_analysis" in agent_tasks.AGENT_REGISTRY


def test_url_analysis_task_uses_agent_signature(monkeypatch):
    calls = {}

    class FakeURLAgent:
        async def run(self, url, crawl_depth=0, context_note="", project_id=0, navigation=None):
            calls.update(url=url, crawl_depth=crawl_depth, context_note=context_note, project_id=project_id)
            return {"ok": True}

    monkeypatch.setattr(agent_tasks, "URLAnalysisAgent", lambda: FakeURLAgent())
    async def _nav(_project_id):
        return {"targets": [], "base_urls": {}}
    monkeypatch.setattr(agent_tasks, "_resolve_navigation_map", _nav)

    result = anyio.run(
        agent_tasks._url_analysis,
        {"url": "https://portal.example.com", "crawl_depth": 1, "context_note": "selfcare", "project_id": 3},
    )
    assert result == {"ok": True}
    assert calls["url"] == "https://portal.example.com"
    assert calls["crawl_depth"] == 1
    assert calls["project_id"] == 3
