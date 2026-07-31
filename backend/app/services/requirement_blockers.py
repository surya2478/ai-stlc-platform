"""What blocks a requirement from advancing, and how each blocker is cleared.

Three problems this module exists to fix, all found on a real project whose
requirements were generated from a crawled URL rather than a specification
document:

1. **Every declared unknown blocked, with no severity.** The old rule was a bare
   `if missing_information:`. One item blocked as hard as ten, which created a
   perverse incentive — a thorough extraction blocked itself harder, and an agent
   that declared nothing sailed through. The approved UI-007 contract already
   said otherwise at Section "Send to Traceability is disabled while *mandatory*
   ambiguity, taxonomy, application mapping or missing-information blockers
   remain"; the code simply did not honour the word *mandatory*.

2. **Taxonomy blockers could be unsatisfiable.** `telecom_domain` maps to a
   telecom-only vocabulary. A requirement crawled from a generic web form belongs
   to none of it, so the agent correctly returns null — and then the gate demanded
   a value no re-run could ever produce. A human can now record that taxonomy
   does not apply, once, with a reason. It is never inferred: contract Section 95
   forbids AI inventing taxonomy, and auto-deciding "this is not telecom" would
   be the same mistake in reverse.

3. **The panel implied one route for every blocker.** Some clear on re-analysis,
   some need a human to type something, some need the requirement owner to answer
   a clarification. Each blocker now states which, so "Re-run Analysis" stops
   being offered as the fix for something it cannot fix.

The blocker list is built here and served to the UI, replacing the parallel
client-side copy in `requirements/page.tsx` that could disagree with this one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Severity = Literal["blocking", "advisory"]
Resolution = Literal["rerun_analysis", "human_input", "clarification"]

# What clearing a blocker actually requires.
#   rerun_analysis — re-running the agent can clear it once the input changed
#   human_input    — a person must record a value or a decision; no re-run helps
#   clarification  — the requirement owner must answer, via Request Clarification
RESOLUTION_LABEL: dict[str, str] = {
    "rerun_analysis": "Re-run Analysis",
    "human_input": "Needs your input",
    "clarification": "Needs an answer from the requirement owner",
}


@dataclass(slots=True)
class MissingInfoItem:
    item: str
    severity: Severity

    @property
    def is_blocking(self) -> bool:
        return self.severity == "blocking"

    def as_dict(self) -> dict[str, str]:
        return {"item": self.item, "severity": self.severity}


@dataclass(slots=True)
class Blocker:
    code: str
    message: str
    resolution: Resolution

    def as_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
            "resolution": self.resolution,
            "resolution_label": RESOLUTION_LABEL[self.resolution],
        }


def normalize_missing_information(raw: Any) -> list[MissingInfoItem]:
    """Accept both the old and new shapes.

    Historical rows store plain strings; the agent now emits
    `{"item": ..., "severity": ...}`. A bare string normalizes to **blocking**,
    deliberately: defaulting legacy data to advisory would retroactively unblock
    requirements that no agent has actually re-judged. Re-running analysis
    reclassifies them properly.
    """
    if not raw:
        return []
    if isinstance(raw, (str, bytes)):
        raw = [raw]
    if not isinstance(raw, (list, tuple)):
        return []

    items: list[MissingInfoItem] = []
    for entry in raw:
        # Guard before str(): `str(None)` is "None", which would otherwise become
        # a blocker reading "Missing information: None".
        if entry is None:
            continue
        if isinstance(entry, dict):
            text = str(entry.get("item") or entry.get("text") or "").strip()
            severity = str(entry.get("severity") or "blocking").strip().lower()
            if severity not in ("blocking", "advisory"):
                severity = "blocking"
        else:
            text = str(entry).strip()
            severity = "blocking"
        if text:
            items.append(MissingInfoItem(item=text, severity=severity))  # type: ignore[arg-type]
    return items


def blocking_missing_information(raw: Any) -> list[MissingInfoItem]:
    return [i for i in normalize_missing_information(raw) if i.is_blocking]


def advisory_missing_information(raw: Any) -> list[MissingInfoItem]:
    return [i for i in normalize_missing_information(raw) if not i.is_blocking]


def taxonomy_waiver(req: Any) -> dict[str, Any] | None:
    """The human record that taxonomy does not apply to this requirement."""
    waiver = (getattr(req, "metadata_", None) or {}).get("taxonomy_not_applicable")
    return waiver if isinstance(waiver, dict) else None


def _has_values(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return bool(str(value).strip())


def analysis_blockers(req: Any) -> list[Blocker]:
    """Everything preventing this requirement from reaching traceability."""
    blockers: list[Blocker] = []

    quality_review = (getattr(req, "metadata_", None) or {}).get("quality_review") or {}
    if quality_review.get("stale") is True:
        blockers.append(
            Blocker(
                "quality_stale",
                "Saved changes have not been validated. Re-run Analysis before traceability.",
                "rerun_analysis",
            )
        )
    elif str(getattr(req, "quality_verdict", "") or "").lower() != "pass":
        # `elif`: a stale review's verdict describes the previous revision, so
        # reporting both would tell the reader to fix a score that is about to be
        # recalculated anyway.
        blockers.append(
            Blocker(
                "quality_not_pass",
                "Quality analysis must reach a Pass verdict. Revise the requirement and re-run Analysis.",
                "rerun_analysis",
            )
        )

    for missing in blocking_missing_information(getattr(req, "missing_information", None)):
        blockers.append(
            Blocker(
                "missing_information",
                f"Missing information: {missing.item}",
                # The agent cannot invent these; only the requirement owner knows.
                "clarification",
            )
        )

    if taxonomy_waiver(req) is None:
        if not _has_values(
            getattr(req, "telecom_domain", None)
            or getattr(req, "qa_domain", None)
            or getattr(req, "business_process", None)
        ):
            blockers.append(
                Blocker(
                    "taxonomy_domain",
                    "Domain or business-process classification is required.",
                    "human_input",
                )
            )
        if not _has_values(
            getattr(req, "product", None)
            or getattr(req, "product_group", None)
            or getattr(req, "sub_request_type", None)
        ):
            blockers.append(
                Blocker(
                    "taxonomy_product",
                    "Product or request-type classification is required.",
                    "human_input",
                )
            )

    return blockers


def traceability_blockers(req: Any) -> list[Blocker]:
    blockers = analysis_blockers(req)
    mapped_systems = (
        getattr(req, "systems_impacted", None)
        or getattr(req, "impacted_systems", None)
        or getattr(req, "impacted_interfaces", None)
        or getattr(req, "upstream_systems", None)
        or getattr(req, "downstream_systems", None)
        or getattr(req, "product", None)
        or getattr(req, "product_group", None)
    )
    if not _has_values(mapped_systems):
        blockers.append(
            Blocker(
                "system_mapping",
                "At least one application, product, system, or interface mapping is required.",
                "human_input",
            )
        )
    return blockers


def summarize(blockers: list[Blocker]) -> dict[str, Any]:
    """Grouped for the UI, so the panel can stop implying one route for all."""
    return {
        "blockers": [b.as_dict() for b in blockers],
        "total": len(blockers),
        "by_resolution": {
            resolution: [b.as_dict() for b in blockers if b.resolution == resolution]
            for resolution in ("rerun_analysis", "human_input", "clarification")
        },
        # True when re-running the agent cannot clear anything that remains — the
        # signal the old panel lacked.
        "rerun_cannot_help": all(b.resolution != "rerun_analysis" for b in blockers)
        and bool(blockers),
    }
