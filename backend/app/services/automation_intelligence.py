"""Rule-based intelligence analyzer for AutomationScript code.

Phase 2D ships heuristic analyzers (no LLM dependency) that look at the script
source and return structured findings the AI Intelligence Assistant panel can
render. The findings are deterministic for a given input, which keeps tests
straightforward and audit logs meaningful.

When real LLM-backed analyzers land, they should produce findings that share
this shape so the frontend doesn't need to know whether a recommendation came
from a rule or a model.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Literal

from app.models.automation_script import AutomationScript


Severity = Literal["low", "medium", "high"]
RecommendationKind = Literal[
    "hard_wait",
    "brittle_locator",
    "missing_assertion",
    "missing_teardown",
    "hardcoded_data",
    "exposed_credential",
    "env_specific_url",
    "duplicate_step",
]


@dataclass(slots=True)
class _Match:
    line: int
    snippet: str


# ─── Regex bank ────────────────────────────────────────────────────────────────

_HARD_WAIT = re.compile(r"\b(?:waitForTimeout|time\.sleep|asyncio\.sleep)\s*\(\s*([0-9_]+)")
_LOCATOR_CSS_ID = re.compile(r"['\"]#([a-zA-Z][\w-]+)['\"]")
_LOCATOR_TESTID = re.compile(r"\[data-testid\s*=\s*['\"]([^'\"]+)['\"]\]")
_LOCATOR_ROLE = re.compile(r"getByRole\(\s*['\"]([^'\"]+)['\"]")
_LOCATOR_LABEL = re.compile(r"\[aria-label\s*=\s*['\"]([^'\"]+)['\"]\]")
_LOCATOR_CLASS = re.compile(r"['\"]\.([a-zA-Z][\w-]+)['\"]")
_LOCATOR_XPATH = re.compile(r"['\"](//[^'\"]+)['\"]")
_LOCATOR_NTH = re.compile(r":nth-child\(\d+\)")
_ASSERT_CALL = re.compile(r"\b(?:expect\(|assert\s)")
_BIZ_ACTION = re.compile(
    r"\b(?:click|press|submit|fill|select|tap)\b.*\b(?:submit|confirm|create|purchase|recharge|pay|checkout)\b",
    re.IGNORECASE,
)
_HARDCODED_PHONE = re.compile(r"['\"](\+?\d{10,15})['\"]")
_HARDCODED_EMAIL = re.compile(r"['\"]([\w._%+-]+@[\w.-]+\.[A-Za-z]{2,})['\"]")
_HARDCODED_URL = re.compile(r"['\"](https?://[^'\"\s]+)['\"]")
_BEARER_TOKEN = re.compile(r"['\"]Bearer\s+[A-Za-z0-9._\-]{16,}['\"]")
_PASSWORD_LIKE = re.compile(r"\bpassword\s*[:=]\s*['\"][^'\"]{4,}['\"]", re.IGNORECASE)
_TEARDOWN_HOOK = re.compile(r"\b(?:afterEach|afterAll|fixture\b|teardown|cleanup)\b", re.IGNORECASE)
_ENV_LEAK_HOSTS = re.compile(r"\b(?:staging|dev|qa|uat|test)\.[\w.-]+\b")


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _stable_id(*parts: object) -> str:
    """Deterministic id so the frontend can apply/dismiss without backend state."""
    raw = "|".join(str(p) for p in parts)
    return "rec_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _scan(pattern: re.Pattern[str], code: str) -> list[_Match]:
    matches: list[_Match] = []
    for m in pattern.finditer(code):
        # Compute 1-based line number for the match start
        line_no = code.count("\n", 0, m.start()) + 1
        snippet = code.splitlines()[line_no - 1].strip() if line_no - 1 < len(code.splitlines()) else m.group(0)
        matches.append(_Match(line=line_no, snippet=snippet[:160]))
    return matches


# ─── Public output shapes ──────────────────────────────────────────────────────


@dataclass(slots=True)
class Recommendation:
    id: str
    kind: RecommendationKind
    title: str
    severity: Severity
    confidence: int
    description: str
    proposal: str
    related: str  # human-friendly source location

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "title": self.title,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "proposal": self.proposal,
            "related": self.related,
        }


@dataclass(slots=True)
class LocatorFinding:
    id: str
    current: str
    current_confidence: int
    suggested: str
    suggested_confidence: int
    rationale: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "current": self.current,
            "current_confidence": self.current_confidence,
            "suggested": self.suggested,
            "suggested_confidence": self.suggested_confidence,
            "rationale": self.rationale,
        }


@dataclass(slots=True)
class AssertionGap:
    id: str
    scenario: str
    missing: str
    suggestion: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "scenario": self.scenario,
            "missing": self.missing,
            "suggestion": self.suggestion,
        }


@dataclass(slots=True)
class DataIssue:
    id: str
    kind: Literal["hardcoded", "unmasked", "expired", "env_leak"]
    description: str
    proposal: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "kind": self.kind,
            "description": self.description,
            "proposal": self.proposal,
        }


@dataclass(slots=True)
class ChecksProposal:
    id: str
    layer: Literal["API", "DB", "Event"]
    title: str
    details: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "layer": self.layer,
            "title": self.title,
            "details": self.details,
        }


@dataclass(slots=True)
class HealthScore:
    overall: int
    parts: list[dict]

    def as_dict(self) -> dict:
        return {"overall": self.overall, "parts": self.parts}


@dataclass(slots=True)
class IntelligenceReport:
    script_id: int
    framework: str
    recommendations: list[Recommendation]
    locators: list[LocatorFinding]
    assertions: list[AssertionGap]
    data_issues: list[DataIssue]
    checks: list[ChecksProposal]
    health: HealthScore

    def as_dict(self) -> dict:
        return {
            "script_id": self.script_id,
            "framework": self.framework,
            "recommendations": [r.as_dict() for r in self.recommendations],
            "locators": [l.as_dict() for l in self.locators],
            "assertions": [a.as_dict() for a in self.assertions],
            "data_issues": [d.as_dict() for d in self.data_issues],
            "checks": [c.as_dict() for c in self.checks],
            "health": self.health.as_dict(),
        }


# ─── Analyzers ────────────────────────────────────────────────────────────────


def _analyze_recommendations(code: str, sid: int) -> list[Recommendation]:
    out: list[Recommendation] = []

    for m in _scan(_HARD_WAIT, code):
        out.append(Recommendation(
            id=_stable_id(sid, "hard_wait", m.line),
            kind="hard_wait",
            title="Hard wait detected",
            severity="high",
            confidence=92,
            description="Fixed-duration waits make the suite slow and flaky.",
            proposal="Replace with an explicit condition-based wait, or assertion-driven auto-wait.",
            related=f"line {m.line}: {m.snippet}",
        ))

    for m in _scan(_LOCATOR_NTH, code):
        out.append(Recommendation(
            id=_stable_id(sid, "brittle_locator", m.line),
            kind="brittle_locator",
            title="Brittle nth-child locator",
            severity="medium",
            confidence=80,
            description="Positional selectors break when layout reorders.",
            proposal="Use [data-testid] or a semantic role + accessible name.",
            related=f"line {m.line}: {m.snippet}",
        ))

    for m in _scan(_LOCATOR_XPATH, code):
        out.append(Recommendation(
            id=_stable_id(sid, "brittle_locator_xpath", m.line),
            kind="brittle_locator",
            title="XPath locator",
            severity="medium",
            confidence=72,
            description="XPath is harder to maintain than role-based locators.",
            proposal="Prefer getByRole / getByLabel; fall back to XPath only when nothing else is stable.",
            related=f"line {m.line}: {m.snippet}",
        ))

    if not _ASSERT_CALL.search(code):
        out.append(Recommendation(
            id=_stable_id(sid, "missing_assertion", 0),
            kind="missing_assertion",
            title="No assertions detected",
            severity="high",
            confidence=88,
            description="The script performs actions but does not verify any expected outcome.",
            proposal="Add at least one assertion against the business outcome (UI text, API status, DB row).",
            related="whole script",
        ))

    if _TEARDOWN_HOOK.search(code) is None and _BIZ_ACTION.search(code):
        out.append(Recommendation(
            id=_stable_id(sid, "missing_teardown", 0),
            kind="missing_teardown",
            title="Missing teardown",
            severity="low",
            confidence=66,
            description="Test creates state (recharge / order / purchase) but does not clean it up.",
            proposal="Add an afterEach / fixture cleanup that reverses the side-effects.",
            related="end of script",
        ))

    for m in _scan(_BEARER_TOKEN, code):
        out.append(Recommendation(
            id=_stable_id(sid, "exposed_credential", m.line),
            kind="exposed_credential",
            title="Bearer token in source",
            severity="high",
            confidence=95,
            description="Hardcoded bearer token is a credential leak.",
            proposal="Read from an env var or secrets manager.",
            related=f"line {m.line}",
        ))

    return out


_LOCATOR_PRIORITY = (
    ("testid", _LOCATOR_TESTID, 92),
    ("role", _LOCATOR_ROLE, 88),
    ("aria_label", _LOCATOR_LABEL, 82),
)


def _analyze_locators(code: str, sid: int) -> list[LocatorFinding]:
    out: list[LocatorFinding] = []
    seen: set[str] = set()

    for m in _scan(_LOCATOR_CSS_ID, code):
        key = f"id:{m.snippet}:{m.line}"
        if key in seen:
            continue
        seen.add(key)
        out.append(LocatorFinding(
            id=_stable_id(sid, "loc", "id", m.line),
            current=m.snippet,
            current_confidence=50,
            suggested='[data-testid="…"]',
            suggested_confidence=92,
            rationale="ids on framework-rendered pages change across builds; data-testid stays stable.",
        ))

    for m in _scan(_LOCATOR_CLASS, code):
        key = f"class:{m.snippet}:{m.line}"
        if key in seen:
            continue
        seen.add(key)
        out.append(LocatorFinding(
            id=_stable_id(sid, "loc", "class", m.line),
            current=m.snippet,
            current_confidence=40,
            suggested='getByRole("button", { name: "…" })',
            suggested_confidence=86,
            rationale="Classes often repeat across the page; role + accessible name is unique.",
        ))

    for m in _scan(_LOCATOR_XPATH, code):
        key = f"xpath:{m.snippet}:{m.line}"
        if key in seen:
            continue
        seen.add(key)
        out.append(LocatorFinding(
            id=_stable_id(sid, "loc", "xpath", m.line),
            current=m.snippet,
            current_confidence=25,
            suggested='[data-testid="…"] or getByLabel("…")',
            suggested_confidence=88,
            rationale="XPath is brittle against layout changes; switch to semantic selectors.",
        ))

    return out


def _analyze_assertions(code: str, sid: int) -> list[AssertionGap]:
    out: list[AssertionGap] = []
    assertion_count = len(list(_ASSERT_CALL.finditer(code)))
    biz_matches = _scan(_BIZ_ACTION, code)

    if biz_matches and assertion_count == 0:
        out.append(AssertionGap(
            id=_stable_id(sid, "assert_business", 0),
            scenario=biz_matches[0].snippet,
            missing="Business action executed but nothing is verified afterwards.",
            suggestion="Add a UI or API assertion that confirms the side-effect (balance change, order created, confirmation visible).",
        ))

    # Specific: recharge/purchase without API balance check
    if re.search(r"\brecharge|purchase|checkout\b", code, re.IGNORECASE) and not re.search(
        r"\bbalance|account/.+/balance\b", code, re.IGNORECASE
    ):
        out.append(AssertionGap(
            id=_stable_id(sid, "assert_balance", 0),
            scenario="Recharge / purchase flow",
            missing="No balance or account-state verification after the transaction.",
            suggestion="Call GET /accounts/{id}/balance and assert the new value matches expected.",
        ))

    return out


def _analyze_data(code: str, sid: int) -> list[DataIssue]:
    out: list[DataIssue] = []

    for m in _scan(_HARDCODED_PHONE, code):
        out.append(DataIssue(
            id=_stable_id(sid, "data_phone", m.line),
            kind="hardcoded",
            description=f"Hardcoded phone-like value on line {m.line}.",
            proposal="Move to a reserved test-data set and read from a fixture.",
        ))

    for m in _scan(_HARDCODED_EMAIL, code):
        out.append(DataIssue(
            id=_stable_id(sid, "data_email", m.line),
            kind="hardcoded",
            description=f"Hardcoded email on line {m.line}.",
            proposal="Generate per-run or fetch from the test-data pool.",
        ))

    for m in _scan(_BEARER_TOKEN, code):
        out.append(DataIssue(
            id=_stable_id(sid, "data_token", m.line),
            kind="unmasked",
            description=f"Bearer token visible in source on line {m.line}.",
            proposal="Read from process.env or a secret reference.",
        ))

    for m in _scan(_PASSWORD_LIKE, code):
        out.append(DataIssue(
            id=_stable_id(sid, "data_password", m.line),
            kind="unmasked",
            description=f"Password-like literal on line {m.line}.",
            proposal="Use an env var; never commit passwords.",
        ))

    for m in _scan(_HARDCODED_URL, code):
        host = m.snippet
        if _ENV_LEAK_HOSTS.search(host):
            out.append(DataIssue(
                id=_stable_id(sid, "data_env_url", m.line),
                kind="env_leak",
                description=f"Environment-specific URL on line {m.line}: {host[:80]}",
                proposal="Read base URL from a typed config helper (process.env.BASE_URL).",
            ))

    return out


def _analyze_checks(code: str, sid: int) -> list[ChecksProposal]:
    out: list[ChecksProposal] = []
    lower = code.lower()

    if "purchase" in lower or "recharge" in lower or "checkout" in lower:
        out.append(ChecksProposal(
            id=_stable_id(sid, "chk_order", 0),
            layer="API",
            title="Verify order creation",
            details="POST /orders should return 201 and an order_id matching the UI confirmation.",
        ))
        out.append(ChecksProposal(
            id=_stable_id(sid, "chk_ledger", 0),
            layer="DB",
            title="Verify ledger entry",
            details="billing.ledger should have one new row with the right txn_type and amount.",
        ))
    if "login" in lower or "signin" in lower:
        out.append(ChecksProposal(
            id=_stable_id(sid, "chk_session", 0),
            layer="API",
            title="Verify session created",
            details="Assert /me returns the authenticated user after the login action.",
        ))

    return out


def _compute_health(
    recommendations: list[Recommendation],
    locators: list[LocatorFinding],
    data_issues: list[DataIssue],
    code: str,
) -> HealthScore:
    # Start from 100 in each dimension and deduct for findings.
    maintainability = 100
    reliability = 100
    readability = 100
    test_data_quality = 100

    for r in recommendations:
        if r.kind == "hard_wait":
            reliability -= 12
        elif r.kind == "brittle_locator":
            maintainability -= 8
        elif r.kind == "missing_assertion":
            reliability -= 15
        elif r.kind == "missing_teardown":
            reliability -= 4
        elif r.kind == "exposed_credential":
            test_data_quality -= 25

    for l in locators:
        if l.current_confidence < 40:
            maintainability -= 6

    for d in data_issues:
        if d.kind in ("unmasked",):
            test_data_quality -= 15
        else:
            test_data_quality -= 6

    # Readability heuristic: long lines drag the score down.
    lines = code.splitlines() or [""]
    long_lines = sum(1 for ln in lines if len(ln) > 140)
    if long_lines:
        readability -= min(30, long_lines * 4)

    def _clamp(x: int) -> int:
        return max(0, min(100, x))

    maintainability = _clamp(maintainability)
    reliability = _clamp(reliability)
    readability = _clamp(readability)
    test_data_quality = _clamp(test_data_quality)
    overall = round((maintainability + reliability + readability + test_data_quality) / 4)

    return HealthScore(
        overall=overall,
        parts=[
            {"label": "Maintainability", "value": maintainability,
             "note": "Locators and structural choices that affect how hard the script is to change."},
            {"label": "Reliability", "value": reliability,
             "note": "Hard waits, missing assertions, and other flakiness sources."},
            {"label": "Readability", "value": readability,
             "note": "Line length, comment density, step clarity."},
            {"label": "Test data quality", "value": test_data_quality,
             "note": "Hardcoded values, exposed credentials, environment leaks."},
        ],
    )


# ─── Public entry point ───────────────────────────────────────────────────────


def analyze_script(script: AutomationScript) -> IntelligenceReport:
    """Run all heuristic analyzers against an AutomationScript and return the report.

    Pure function over (script.id, script.framework, script.code) — easy to cache
    and easy to test.
    """
    code = script.code or ""
    sid = script.id
    recs = _analyze_recommendations(code, sid)
    locs = _analyze_locators(code, sid)
    asserts = _analyze_assertions(code, sid)
    data = _analyze_data(code, sid)
    checks = _analyze_checks(code, sid)
    health = _compute_health(recs, locs, data, code)
    return IntelligenceReport(
        script_id=sid,
        framework=script.framework,
        recommendations=recs,
        locators=locs,
        assertions=asserts,
        data_issues=data,
        checks=checks,
        health=health,
    )


def record_decision(
    script: AutomationScript,
    *,
    recommendation_id: str,
    action: Literal["apply", "dismiss"],
    user_id: int,
    notes: str | None = None,
) -> dict:
    """Append a decision entry to the script's metadata audit log.

    Phase 2D does not modify the script code when 'apply' is chosen; the panel
    surfaces a "Applied as draft change" indicator and Phase 2E (script editor)
    will materialize the actual change. The audit ledger is the source of truth.
    """
    from datetime import datetime, timezone

    log = list((script.metadata_ or {}).get("recommendation_decisions", []))
    entry = {
        "recommendation_id": recommendation_id,
        "action": action,
        "user_id": user_id,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    if notes:
        entry["notes"] = notes
    log.append(entry)
    script.metadata_ = {**(script.metadata_ or {}), "recommendation_decisions": log}
    return entry
