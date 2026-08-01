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
