"""The locator catalog script generation grounds against.

Two stores describe the same application. `locator_map` is a flat,
last-write-wins knowledge base written straight from discovery captures (and
from the recorder's IR emitter). The Application Model is the governed one:
built from a completed discovery session, reviewed, approved and published as
an immutable version, with per-element locator history that a human can
confirm, mark unstable or add fallbacks to.

Generation only ever read `locator_map`. That made publishing a model a
governance ceremony with no teeth — the reviewed, approved artefact had no
effect on the scripts, which kept grounding on whatever the last capture
happened to write, including elements a reviewer had explicitly marked
unstable.

This module makes the published model the source of truth when there is one,
and leaves `locator_map` as the source when there is not, so projects that
have never published a model generate exactly as they did before.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.application_model import (
    ApplicationModel,
    ApplicationModelLocatorEvidence,
    ApplicationModelNode,
)
from app.services import locator_map_service

logger = logging.getLogger(__name__)

# Evidence statuses that mean "do not generate against this".
#
# "unstable" is a reviewer's explicit judgement that the locator does not hold
# — the Application Model raises an UNSTABLE_LOCATOR gap for exactly this, and
# honouring it is most of the point of grounding on the model rather than on
# the raw capture.
_REJECTED_EVIDENCE_STATUSES = frozenset({"unstable"})


@dataclass
class LocatorCatalog:
    """Catalog entries plus where they came from.

    `source` is recorded rather than inferred so a generated script can say
    truthfully what it was grounded on, and so a thin catalog can be traced to
    a thin model instead of looking like a generation bug.
    """

    entries: list[dict[str, Any]] = field(default_factory=list)
    source: str = "none"  # "application_model" | "locator_map" | "none"
    model_id: int | None = None
    model_version: int | None = None

    def __bool__(self) -> bool:
        return bool(self.entries)


async def get_published_model(
    db: AsyncSession, *, project_id: int, application_id: int
) -> ApplicationModel | None:
    """The application's current published model version, if any.

    `publish` demotes the previous published row to "superseded" in the same
    transaction, so at most one row can match. Ordered by version anyway, so a
    historical row that escaped that invariant cannot silently win.
    """
    result = await db.execute(
        select(ApplicationModel)
        .where(
            ApplicationModel.project_id == project_id,
            ApplicationModel.application_id == application_id,
            ApplicationModel.status == "published",
        )
        .order_by(ApplicationModel.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _current_evidence(
    evidence: list[ApplicationModelLocatorEvidence],
) -> tuple[ApplicationModelLocatorEvidence | None, bool]:
    """The locator currently recommended for one element node, and whether a
    reviewer ruled the element out.

    The evidence table is append-only — confirm, mark-unstable and add-fallback
    each insert a row rather than mutate — so the newest row that actually
    carries a locator is the current recommendation. A newest row of "unstable"
    means a reviewer has ruled the element out; fall through to an explicit
    fallback if one was added after it, otherwise return nothing so the element
    is left out of the catalog entirely.

    The second value separates "a reviewer rejected this" from "this element
    never had a locator". They look identical here — both yield no entry — but
    they must not be treated the same once `locator_map` can fill gaps: a
    rejection has to suppress the map's copy too, or the veto is undone by the
    back door. Missing evidence carries no such judgement.
    """
    ordered = sorted(evidence, key=lambda row: (row.created_at, row.id), reverse=True)
    with_locator = [row for row in ordered if row.locator_value]
    if not with_locator:
        return None, False
    newest = with_locator[0]
    if newest.status not in _REJECTED_EVIDENCE_STATUSES:
        return newest, False
    fallback = next((row for row in with_locator if row.status == "fallback"), None)
    return fallback, fallback is None


def _screen_page_url(
    node: ApplicationModelNode, nodes_by_id: dict[int, ApplicationModelNode]
) -> str:
    """The page this element was discovered on.

    Prefers the real URL recorded on the element at build time. Older models
    were built before that was captured, so fall back to walking up to the
    screen node and using its reference — a slug rather than a URL, which
    `locator_policy.filter_catalog_by_page` cannot host-match, so it degrades
    to an unscoped catalog rather than to a wrong one.
    """
    page_url = (node.attributes or {}).get("page_url")
    if page_url:
        return str(page_url)
    current = node
    seen: set[int] = set()
    while current.parent_node_id is not None and current.parent_node_id not in seen:
        seen.add(current.parent_node_id)
        parent = nodes_by_id.get(current.parent_node_id)
        if parent is None:
            break
        if parent.node_type == "screen":
            return parent.external_ref
        current = parent
    return ""


def _catalog_name(node: ApplicationModelNode) -> str:
    """The name generated contracts refer this element by.

    `catalog_name` is the slug `locator_map` is keyed by, so a model-sourced
    catalog names elements identically to the map-sourced one it replaces —
    contracts, prompts and `ground_page_object_elements` all keep matching.
    `external_ref` is a slug of the *step's* wording, which is a different and
    much noisier thing, so it is only the fallback.
    """
    name = (node.attributes or {}).get("catalog_name")
    if name:
        return str(name)
    return node.external_ref.removeprefix("element-") or node.external_ref


async def _entries_from_model(
    db: AsyncSession, model: ApplicationModel
) -> tuple[list[dict[str, Any]], set[str]]:
    """This model's catalog entries, and the names it deliberately withholds.

    The second value is the reviewer veto, carried out of here so the merge in
    `build_for_application` can honour it against `locator_map` as well.
    """
    result = await db.execute(
        select(ApplicationModelNode)
        .options(selectinload(ApplicationModelNode.locator_evidence))
        .where(ApplicationModelNode.model_id == model.id)
    )
    nodes = list(result.scalars().all())
    nodes_by_id = {node.id: node for node in nodes}

    entries: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    suppressed: set[str] = set()
    for node in nodes:
        if node.node_type != "element":
            continue
        evidence, rejected = _current_evidence(list(node.locator_evidence))
        name = _catalog_name(node)
        if rejected:
            suppressed.add(name)
        if evidence is None:
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        entries.append({
            "element_name": name,
            "page": _screen_page_url(node, nodes_by_id),
            "role": evidence.locator_type,
            # The step wording that found this element is the most useful
            # description available, and it is what relevance-ranks a catalog
            # against a test case in locator_policy.
            "business_meaning": node.description or node.display_name,
            "recommended_locator": evidence.locator_value,
            "confidence_score": evidence.confidence or 0,
        })
    return entries, suppressed


def _entries_from_locator_map(rows: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "element_name": row.element_name,
            "page": row.page,
            "role": row.recommended_strategy,
            "business_meaning": row.business_meaning,
            "recommended_locator": row.recommended_locator,
            "confidence_score": row.confidence_score,
        }
        for row in rows
    ]


async def build_for_application(
    db: AsyncSession, *, project_id: int, application_id: int | None
) -> LocatorCatalog:
    """The catalog to ground one application's scripts against.

    The published Application Model supplies every element it has a reviewed
    locator for; `locator_map` fills in the rest.

    The model used to win *outright*, on the reasoning that the two stores name
    elements by different schemes and merging would put one physical control in
    the catalog twice under two names — the exact ambiguity
    `ground_page_object_elements` cannot resolve. That reasoning held when it
    was written and no longer does: model element nodes now carry
    `catalog_name`, which IS the `locator_map` key (it was added so the model
    could serve as a catalog at all), so the two are keyed in one namespace and
    a merge cannot double-name anything.

    Winning outright had a cost that only showed up in the numbers. The model
    contains one element per step discovery *acted on*; `locator_map` contains
    everything the page crawl saw. On a live project that was 1 element against
    97 — so publishing a model shrank the generation catalog by two orders of
    magnitude, and assertions the generator could otherwise have grounded were
    dropped for want of a target.

    The reviewer veto survives the merge: an element ruled unstable with no
    fallback is suppressed from BOTH stores, so filling gaps from the map can
    never quietly reinstate a locator a human rejected.
    """
    if application_id is None:
        return LocatorCatalog()

    model = await get_published_model(db, project_id=project_id, application_id=application_id)
    model_entries: list[dict[str, Any]] = []
    suppressed: set[str] = set()
    if model is not None:
        model_entries, suppressed = await _entries_from_model(db, model)
        if not model_entries:
            logger.info(
                "locator_catalog: published model %s (v%s) for application %s has no element with a "
                "usable locator — grounding on locator_map alone",
                model.id, model.version, application_id,
            )

    rows = await locator_map_service.list_for_application(
        db, project_id=project_id, application_id=application_id
    )
    known = {entry["element_name"] for entry in model_entries}
    map_entries = [
        entry for entry in _entries_from_locator_map(rows)
        if entry["element_name"] not in known and entry["element_name"] not in suppressed
    ]

    if model_entries and map_entries:
        source = "application_model+locator_map"
    elif model_entries:
        source = "application_model"
    elif map_entries:
        source = "locator_map"
    else:
        source = "none"

    return LocatorCatalog(
        entries=[*model_entries, *map_entries],
        source=source,
        model_id=model.id if model else None,
        model_version=model.version if model else None,
    )
