"""Known navigation targets for a project, harvested from what was observed.

A screenshot cannot tell you where a button goes, so requirements derived from
one declared "Exact URLs for each navigation target" as blocking and waited on a
human. But the project usually already knows: an application is registered with
environment URLs, and any page of the same site analysed from a live URL carried
a DOM inventory of `{label, href, url}` for every anchor.

This assembles that into one map the derivation agents can be given as ground
truth, so a destination the platform has already seen is never asked of a person
again.

**Observed, never inferred.** Every entry here came from a rendered page's
markup. Nothing guesses that "About" lives at `/about` because that is the usual
convention — a map built by convention would be wrong exactly where a site is
unusual, and wrong silently. A label with no observed destination stays unknown,
which is the honest answer and keeps the existing blocker meaningful.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_application import ProjectApplication
from app.models.requirement import Requirement
from app.services.url_capture_service import capture_pages, link_inventory

logger = logging.getLogger(__name__)

# A screenshot's label and a DOM anchor's label rarely match character for
# character — "Services Page" in a screen description versus "Services" in the
# markup. These suffixes are stripped for comparison only; the stored label is
# always the one actually observed.
_LABEL_NOISE = (" page", " link", " button", " tab", " screen")

MAX_TARGETS = 60


def normalize_label(label: str) -> str:
    text = (label or "").strip().casefold()
    changed = True
    while changed:
        changed = False
        for suffix in _LABEL_NOISE:
            if text.endswith(suffix):
                text = text[: -len(suffix)].strip()
                changed = True
    return text


def merge_link_inventories(inventories: list[Any]) -> list[dict]:
    """Flatten link inventories into one deduplicated target list.

    Deduplicates on the resolved URL rather than the label: the same destination
    reached from a header and a footer is one target, and keeping both would
    pad the prompt with repetition. The first label seen wins, since earlier
    inventories come from more recently analysed pages.
    """
    targets: list[dict] = []
    seen_urls: set[str] = set()
    for inventory in inventories or []:
        if not isinstance(inventory, list):
            continue
        for link in inventory:
            if not isinstance(link, dict):
                continue
            url = str(link.get("url") or "").strip()
            label = str(link.get("label") or "").strip()
            # A target with no destination is exactly what this map exists to
            # avoid claiming, and an unlabelled one cannot be matched to a
            # screen element.
            if not url or not label:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            targets.append({"label": label, "url": url})
            if len(targets) >= MAX_TARGETS:
                return targets
    return targets


async def project_navigation_map(db: AsyncSession, project_id: int) -> dict:
    """Everything this project has observed about where its navigation goes."""
    if not project_id:
        return {"targets": [], "base_urls": {}}

    rows = (
        await db.execute(
            select(Requirement.metadata_)
            .where(Requirement.project_id == project_id)
            .order_by(Requirement.id.desc())
            .limit(50)
        )
    ).scalars().all()

    inventories = []
    for metadata in rows:
        links = ((metadata or {}).get("ui_analysis") or {}).get("links")
        if links:
            inventories.append(links)

    base_urls: dict[str, str] = {}
    apps = (
        await db.execute(
            select(ProjectApplication).where(
                ProjectApplication.project_id == project_id,
                ProjectApplication.is_active.is_(True),
            )
        )
    ).scalars().all()
    for app in apps:
        for env, url in (app.environment_urls or {}).items():
            if url:
                base_urls[f"{app.name} ({env})"] = url

    return {"targets": merge_link_inventories(inventories), "base_urls": base_urls}


async def harvest_base_url(base_url: str) -> list[dict]:
    """Read one configured application URL for its navigation targets.

    The fallback for the ordering problem: a project whose requirements all came
    from screenshots has no observed links yet, so without this the operator
    would have to run a URL analysis first and re-run the image ones after —
    exactly the manual sequencing this map exists to remove.

    Depth 0 and best effort. An unreachable or slow site must degrade to "no
    observed targets", never fail the analysis that asked.
    """
    if not base_url:
        return []
    try:
        pages = await capture_pages(base_url, crawl_depth=0)
    except Exception:
        logger.warning("Could not harvest navigation targets from %s", base_url, exc_info=True)
        return []
    inventories = [link_inventory(p.url, p.dom_summary) for p in pages]
    return merge_link_inventories(inventories)


async def resolve(db: AsyncSession, project_id: int) -> dict:
    """The map an analysis agent should be given.

    Prefers what the project has already observed; falls back to reading a
    configured application URL when nothing has been analysed yet.
    """
    nav = await project_navigation_map(db, project_id)
    if nav["targets"] or not nav["base_urls"]:
        return nav
    first_url = next(iter(nav["base_urls"].values()), "")
    nav["targets"] = await harvest_base_url(first_url)
    return nav


def render_navigation_prompt(nav: dict) -> str:
    """The map as prompt text, or empty when nothing was observed.

    Returning "" for an empty map matters: a heading followed by no entries
    reads to a model as "there are no navigation targets", which is a stronger
    and different claim than "none have been observed yet".
    """
    targets = (nav or {}).get("targets") or []
    base_urls = (nav or {}).get("base_urls") or {}
    if not targets and not base_urls:
        return ""

    lines = ["", "KNOWN NAVIGATION TARGETS FOR THIS PROJECT (observed, not inferred)."]
    if base_urls:
        lines.append("Configured application base URLs:")
        for name, url in base_urls.items():
            lines.append(f"  - {name}: {url}")
    if targets:
        lines.append(
            "Destinations already read from this application's own markup "
            "(label -> resolved URL):"
        )
        for target in targets:
            lines.append(f"  - {target['label']} -> {target['url']}")

    lines += [
        "",
        "Use these when the screen you are analysing references one of them, "
        "matching on the visible label even if the wording differs slightly "
        "(\"Services Page\" is the \"Services\" target). Put the resolved URL in "
        "`ui_pages` beside the page name and reference it in acceptance "
        "criteria for navigation behaviour.",
        "",
        "Do NOT report a destination listed above as missing information — it "
        "is known. Equally, do NOT invent a URL for a label that is absent from "
        "the list, and do not derive one by convention from the base URL: an "
        "unobserved destination is genuinely unknown and must stay in "
        "`missing_information`.",
    ]
    return "\n".join(lines)
