"""Grounded Automation PoC — testing-type routing (TC-level AND step-level).

Implements the solution design's routing decision matrix as a deterministic,
rules-first classifier: keyword indicators per testing type, applied to the
whole test case AND to every individual step and its expected result — a
telecom TC is frequently hybrid (API create → UI order → Kafka verify → DB
validate), so one TC-level label is not enough to drive execution.

Deliberately no LLM in this pass: routing must be reproducible and auditable
for the gate to be trustworthy. Ambiguous cases get low confidence and a
manual-review flag instead of a guess; an LLM-assist pass for low-confidence
cases is documented Phase-2 work.

PoC adapter availability: only "playwright_web" is executable end-to-end
today. Every other type still classifies and routes correctly, but its
route carries implemented=False + a target phase — that is the PoC's
"routing-only demonstration" of full testing-type coverage.
"""
from __future__ import annotations

import re
from typing import Any

# (type, adapter, implemented, target_phase, patterns)
# Order matters: first match wins per text fragment; UI is the fallback.
_TYPE_RULES: list[dict[str, Any]] = [
    {
        "type": "api",
        "adapter": "api_client",
        "implemented": False,
        "target_phase": "PoC Phase 2",
        "tools": "Playwright API / REST Assured / Newman",
        "patterns": [
            r"\bapi\b", r"\brest\b", r"\bsoap\b", r"\bgraphql\b", r"\bendpoint\b",
            r"\bstatus\s*code\b", r"\bresponse\s*(code|body|payload)\b", r"\bhttp\b",
            r"\bprovisioning\s+status\b.*\bapi\b",
        ],
    },
    {
        "type": "database",
        "adapter": "db_validator",
        "implemented": False,
        "target_phase": "PoC Phase 2",
        "tools": "SQL clients / pytest+JDBC adapters",
        "patterns": [
            r"\bdatabase\b", r"\bdb\b", r"\bsql\b", r"\btable\b", r"\bcolumn\b",
            r"\brecord\s+(in|is|exists)\b", r"\bbilling\s+(record|event|entry)\b",
            r"\bstored\s+procedure\b",
            # NOT a bare \bquery\b — that also matches "search query" / "user
            # query" (UI/search terms), a false positive confirmed live: a
            # step reading "enter the search query into the search box" was
            # misrouted to db_validator. Require explicit DB context instead.
            r"\b(sql|db|database)\s+query\b", r"\bquery\s+the\s+(database|db|table)\b",
            r"\brun\s+(a\s+)?(sql\s+)?query\b",
        ],
    },
    {
        "type": "mobile",
        "adapter": "appium",
        "implemented": False,
        "target_phase": "Later phase",
        "tools": "Appium + device cloud",
        "patterns": [
            r"\bmobile\s+app\b", r"\bandroid\b", r"\bios\b", r"\bdevice\b",
            r"\bself[- ]?care\s+app\b", r"\bapp\s+notification\b",
        ],
    },
    {
        "type": "messaging",
        "adapter": "kafka_rabbitmq",
        "implemented": False,
        "target_phase": "Later phase",
        "tools": "Kafka/RabbitMQ adapters, WireMock, contract tests",
        "patterns": [
            r"\bkafka\b", r"\brabbitmq\b", r"\bqueue\b", r"\btopic\b",
            r"\bevent\s+(is\s+)?(published|consumed|received)\b", r"\bcdr\b",
            r"\bmessage\s+(is\s+)?(sent|received|published)\b", r"\basync\b",
        ],
    },
    {
        "type": "performance",
        "adapter": "k6_jmeter",
        "implemented": False,
        "target_phase": "Later phase",
        "tools": "k6 / JMeter / Gatling",
        "patterns": [
            r"\bload\s+test\b", r"\bconcurrent\s+users?\b", r"\btps\b",
            r"\bresponse\s+time\b", r"\bthroughput\b", r"\bperformance\b",
            r"\bendurance\b", r"\bstress\b", r"\bramp[- ]?up\b",
        ],
    },
    {
        "type": "accessibility",
        "adapter": "axe_core",
        "implemented": False,
        "target_phase": "PoC Phase 2",
        "tools": "axe-core with Playwright",
        "patterns": [
            r"\bwcag\b", r"\baccessibilit\w+\b", r"\bscreen\s+reader\b",
            r"\bcontrast\b", r"\bkeyboard\s+navigation\b", r"\bfocus\s+order\b",
        ],
    },
    {
        "type": "visual",
        "adapter": "visual_diff",
        "implemented": False,
        "target_phase": "PoC Phase 2",
        "tools": "Playwright screenshots + approved baselines",
        "patterns": [
            r"\bvisual\b", r"\blayout\b", r"\brender(ing|ed)?\b",
            r"\bpixel\b", r"\bscreenshot\s+comparison\b", r"\bresponsive\b",
        ],
    },
    {
        "type": "manual",
        "adapter": "human_task",
        "implemented": True,  # routing a step to a human IS the implementation
        "target_phase": "Available now",
        "tools": "Human task with AI guidance + evidence capture",
        "patterns": [
            r"\bsim\s+card\b", r"\bphysical\b", r"\bfield\s+(visit|installation)\b",
            r"\bnetwork\s+coverage\b", r"\botp\s+(received|sent)\s+on\b",
            r"\bhandset\b", r"\bhardware\b", r"\bexplorator\w+\b",
        ],
    },
]

_UI_ROUTE = {
    "type": "web_ui",
    "adapter": "playwright_web",
    "implemented": True,
    "target_phase": "Available now",
    "tools": "Playwright + Playwright MCP capture",
}

# Verbs that indicate a step mutates state → cleanup grounding applies.
_MUTATING_RE = re.compile(
    r"\b(create|submit|add|delete|remove|update|modify|activate|deactivate|register|place|order|recharge|cancel)\b",
    re.IGNORECASE,
)


def _classify_text(text: str) -> tuple[dict[str, Any], int]:
    """Return (route, confidence 0-100) for one text fragment."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return dict(_UI_ROUTE), 40
    for rule in _TYPE_RULES:
        hits = [p for p in rule["patterns"] if re.search(p, lowered)]
        if hits:
            confidence = min(95, 70 + 10 * len(hits))
            route = {k: rule[k] for k in ("type", "adapter", "implemented", "target_phase", "tools")}
            route["matched_indicators"] = hits[:5]
            return route, confidence
    # No non-UI indicator matched → default to web UI with moderate
    # confidence (the capture walk itself will confirm or refute it).
    return dict(_UI_ROUTE), 60


def _step_texts(step: Any) -> tuple[str, str]:
    """(action_text, expected_text) for one raw TC step (dict or string)."""
    if isinstance(step, dict):
        action = str(step.get("action") or step.get("description") or "")
        expected = str(step.get("expected_result") or "")
        return action, expected
    return str(step), ""


def route_test_case(test_case: dict[str, Any]) -> dict[str, Any]:
    """Classify a test case at TC level and step level.

    Returns a routing document stored verbatim on PocGroundingRun.routing:
    {
      "overall": {type, adapter, implemented, ...},
      "overall_confidence": int,
      "is_hybrid": bool,
      "steps": [{index, action_route, action_confidence,
                 assertion_route, assertion_confidence,
                 mutating, requires_cleanup}],
      "unimplemented_adapters": [...],
      "manual_review_recommended": bool,
    }
    """
    steps = test_case.get("steps") or []
    step_routes: list[dict[str, Any]] = []
    type_counts: dict[str, int] = {}

    for index, raw_step in enumerate(steps):
        action_text, expected_text = _step_texts(raw_step)
        action_route, action_conf = _classify_text(action_text)
        # Assertions get their own channel: "verify charge in billing DB"
        # must route to db_validator even when the action was pure UI.
        if expected_text.strip():
            assertion_route, assertion_conf = _classify_text(expected_text)
        else:
            assertion_route, assertion_conf = dict(action_route), action_conf
        mutating = bool(_MUTATING_RE.search(action_text))
        step_routes.append({
            "index": index,
            "action_text": action_text[:300],
            "expected_text": expected_text[:300],
            "action_route": action_route,
            "action_confidence": action_conf,
            "assertion_route": assertion_route,
            "assertion_confidence": assertion_conf,
            "mutating": mutating,
            "requires_cleanup": mutating,
        })
        type_counts[action_route["type"]] = type_counts.get(action_route["type"], 0) + 1
        type_counts[assertion_route["type"]] = type_counts.get(assertion_route["type"], 0) + 1

    # TC-level classification: test_type field first, then dominant step type.
    tc_level_text = " ".join(
        str(test_case.get(k) or "") for k in ("test_type", "title", "expected_result")
    )
    tc_route, tc_conf = _classify_text(tc_level_text)
    dominant = max(type_counts, key=type_counts.get) if type_counts else tc_route["type"]
    distinct_types = {t for t in type_counts if t != "web_ui"}
    is_hybrid = len(type_counts) > 1 and bool(distinct_types)
    if dominant != tc_route["type"] and type_counts.get(dominant, 0) > 1:
        # Step evidence outweighs the TC-level label.
        for rule in _TYPE_RULES:
            if rule["type"] == dominant:
                tc_route = {k: rule[k] for k in ("type", "adapter", "implemented", "target_phase", "tools")}
                break
        else:
            tc_route = dict(_UI_ROUTE)

    unimplemented = sorted({
        r[key]["adapter"]
        for r in step_routes
        for key in ("action_route", "assertion_route")
        if not r[key]["implemented"]
    })
    low_confidence = any(
        r["action_confidence"] < 60 or r["assertion_confidence"] < 60 for r in step_routes
    )

    return {
        "overall": tc_route,
        "overall_confidence": tc_conf,
        "is_hybrid": is_hybrid,
        "type_counts": type_counts,
        "steps": step_routes,
        "unimplemented_adapters": unimplemented,
        "manual_review_recommended": low_confidence or bool(unimplemented),
    }
