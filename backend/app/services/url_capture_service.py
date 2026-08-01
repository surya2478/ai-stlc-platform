"""
Portal URL capture service (GAP-2).

Renders application pages with Playwright (Chromium), extracts a DOM summary
(forms, inputs, validation attributes, buttons, links, navigation) and takes a
full-page screenshot for the vision pass.

Safety:
  - http/https only
  - private/loopback/link-local/reserved IPs are blocked (SSRF guard)
  - same-origin crawling only, with depth and page-count caps
  - analysed pages are never executed beyond rendering; no credentials are sent
"""
from __future__ import annotations

import ipaddress
import logging
import socket
from dataclasses import dataclass, field
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)

MAX_CRAWL_DEPTH = 2
MAX_PAGES = 5
PAGE_TIMEOUT_MS = 30_000

# JS evaluated in the page to build a deterministic DOM inventory.
DOM_SUMMARY_JS = """
() => {
  const text = (el) => (el?.innerText || el?.value || el?.getAttribute('aria-label') || '').trim().slice(0, 80);
  const fields = [];
  document.querySelectorAll('input, select, textarea').forEach((el) => {
    if (['hidden', 'submit', 'button'].includes(el.type)) return;
    const labelEl = el.labels && el.labels[0];
    fields.push({
      name: el.name || el.id || el.placeholder || text(labelEl) || 'unnamed',
      label: text(labelEl) || el.placeholder || '',
      tag: el.tagName.toLowerCase(),
      type: el.type || el.tagName.toLowerCase(),
      required: el.required || el.getAttribute('aria-required') === 'true',
      pattern: el.getAttribute('pattern') || null,
      minlength: el.getAttribute('minlength') || null,
      maxlength: el.getAttribute('maxlength') || null,
      min: el.getAttribute('min') || null,
      max: el.getAttribute('max') || null,
      options: el.tagName === 'SELECT'
        ? Array.from(el.options).slice(0, 15).map((o) => o.text.trim()).filter(Boolean)
        : undefined,
    });
  });
  const buttons = [];
  document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]').forEach((el) => {
    const label = text(el);
    if (label) buttons.push({ label, type: el.type || 'button' });
  });
  const links = [];
  document.querySelectorAll('a[href]').forEach((el) => {
    const label = text(el);
    const href = el.getAttribute('href');
    if (href && !href.startsWith('javascript:')) links.push({ label, href });
  });
  const forms = Array.from(document.querySelectorAll('form')).map((f) => ({
    action: f.getAttribute('action') || '',
    method: (f.getAttribute('method') || 'get').toLowerCase(),
    field_count: f.querySelectorAll('input, select, textarea').length,
  }));
  const headings = Array.from(document.querySelectorAll('h1, h2')).slice(0, 10).map(text).filter(Boolean);
  return {
    title: document.title,
    headings,
    forms,
    fields: fields.slice(0, 60),
    buttons: buttons.slice(0, 40),
    links: links.slice(0, 80),
  };
}
"""


MAX_LINKS = 30


def link_inventory(page_url: str, dom_summary: dict) -> list[dict]:
    """Label *and* destination for every anchor the DOM inventory captured.

    This used to be `[l.get("label") or l.get("href") for l in ...]`, which kept
    the href only when a link had no text. Real navigation links almost always
    have text, so the URL was discarded essentially every time: the derivation
    step received `["Home", "About", "Services"]` and — correctly, given its
    input — reported "Exact URLs for each navigation target" as *blocking*
    missing information, for a page the platform had just rendered and read the
    hrefs from. The requirement then sat waiting on a human for an answer the
    system already had.

    `href` is kept as authored (relative links are what a tester reads in the
    markup) alongside the resolved absolute `url`, which is what an automated
    check actually needs.
    """
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for link in dom_summary.get("links") or []:
        if not isinstance(link, dict):
            continue
        href = str(link.get("href") or "").strip()
        if not href:
            continue
        label = str(link.get("label") or "").strip()
        try:
            absolute = urljoin(page_url, href)
        except ValueError:
            # A malformed href is still worth reporting as a link the page
            # declares; it just has no resolvable destination.
            absolute = href
        key = (label.lower(), absolute)
        if key in seen:
            continue
        seen.add(key)
        out.append({"label": label, "href": href, "url": absolute})
        if len(out) >= MAX_LINKS:
            break
    return out


class UnsafeURLError(ValueError):
    """Raised when a URL fails SSRF/scheme validation."""


@dataclass
class CapturedPage:
    url: str
    title: str
    dom_summary: dict
    screenshot_png: bytes
    same_origin_links: list[str] = field(default_factory=list)


def validate_url_safety(url: str) -> str:
    """Validate scheme and resolve the host, rejecting private/reserved IPs.

    Returns the normalised URL. Raises UnsafeURLError when unsafe.
    """
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https"):
        raise UnsafeURLError("Only http:// and https:// URLs are supported")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no hostname")

    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Could not resolve host '{host}'") from exc

    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            raise UnsafeURLError(
                f"URL resolves to a private/reserved address ({ip}) — blocked for safety"
            )
    return parsed.geturl()


def _same_origin(base_url: str, candidate: str) -> bool:
    b, c = urlparse(base_url), urlparse(candidate)
    return (b.scheme, b.hostname, b.port) == (c.scheme, c.hostname, c.port)


def _extract_same_origin_links(page_url: str, dom_summary: dict) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for link in dom_summary.get("links", []):
        href = (link.get("href") or "").split("#")[0].strip()
        if not href:
            continue
        absolute = urljoin(page_url, href)
        if not _same_origin(page_url, absolute):
            continue
        if absolute in seen or absolute.rstrip("/") == page_url.rstrip("/"):
            continue
        seen.add(absolute)
        result.append(absolute)
    return result


async def capture_pages(
    url: str,
    crawl_depth: int = 0,
    max_pages: int = MAX_PAGES,
) -> list[CapturedPage]:
    """Render `url` (and optionally same-origin links up to `crawl_depth`)
    and return DOM summaries + screenshots.

    Requires Playwright + Chromium in the worker image
    (`pip install playwright && playwright install --with-deps chromium`).
    """
    from playwright.async_api import async_playwright

    crawl_depth = max(0, min(crawl_depth, MAX_CRAWL_DEPTH))
    max_pages = max(1, min(max_pages, MAX_PAGES))

    start_url = validate_url_safety(url)
    captured: list[CapturedPage] = []
    visited: set[str] = set()
    queue: list[tuple[str, int]] = [(start_url, 0)]

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        try:
            while queue and len(captured) < max_pages:
                page_url, depth = queue.pop(0)
                norm = page_url.rstrip("/")
                if norm in visited:
                    continue
                visited.add(norm)
                try:
                    # Re-validate each URL (crawled links could differ in host)
                    validate_url_safety(page_url)
                    page = await context.new_page()
                    await page.goto(page_url, timeout=PAGE_TIMEOUT_MS, wait_until="networkidle")
                    dom_summary = await page.evaluate(DOM_SUMMARY_JS)
                    screenshot = await page.screenshot(full_page=True, type="png")
                    await page.close()
                except UnsafeURLError:
                    logger.warning("Skipping unsafe crawled URL: %s", page_url)
                    continue
                except Exception:
                    logger.exception("Failed to capture page: %s", page_url)
                    continue

                links = _extract_same_origin_links(page_url, dom_summary)
                captured.append(
                    CapturedPage(
                        url=page_url,
                        title=dom_summary.get("title") or page_url,
                        dom_summary=dom_summary,
                        screenshot_png=screenshot,
                        same_origin_links=links,
                    )
                )
                if depth < crawl_depth:
                    for link in links:
                        if link.rstrip("/") not in visited:
                            queue.append((link, depth + 1))
        finally:
            await browser.close()

    if not captured:
        raise RuntimeError(f"Could not capture any page from {url}")
    return captured
