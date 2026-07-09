"""
Automation Eligibility Agent (Phase 2.7) — static pass.

Replaces the one-shot `automation_candidate` boolean the test-case generator
used to guess with a real, auditable verdict: rule-based (no LLM call) over
the test case's own text — title, preconditions, steps, expected result.
Looks for manual-only signals (OTP/CAPTCHA/biometric), environment
dependencies (physical hardware, on-site access), and classifies the
automation style (ui/api/mixed) as a hint for the Script Compiler.

This is "pass 1" per the plan: confirms UI availability from text alone.
Pass 2 (confirming from live page evidence, e.g. an OTP challenge actually
appearing) is Phase 3's job once Playwright MCP discovery exists.
"""
from __future__ import annotations

import re

from app.agents.base.base_agent import AgentRunResult, BaseAgent

Verdict = str  # "yes" | "no" | "unknown"

_MANUAL_ONLY_PATTERNS = [
    (re.compile(r"\bOTP\b", re.IGNORECASE), "requires an OTP challenge"),
    (re.compile(r"\bCAPTCHA\b", re.IGNORECASE), "requires solving a CAPTCHA"),
    (re.compile(r"\bbiometric|fingerprint|face\s*id\b", re.IGNORECASE), "requires biometric verification"),
    (re.compile(r"\bmanual(?:ly)?\s+verif", re.IGNORECASE), "explicitly requires manual verification"),
    (re.compile(r"\bphone\s+call|call\s+center\b", re.IGNORECASE), "requires a phone call / call-center step"),
    (re.compile(r"\bhardware\s+token\b", re.IGNORECASE), "requires a physical hardware token"),
    (re.compile(r"\bin[- ]person\b", re.IGNORECASE), "requires an in-person step"),
]

_ENVIRONMENT_DEPENDENCY_PATTERNS = [
    (re.compile(r"\bphysical\s+SIM\b", re.IGNORECASE), "depends on a physical SIM card"),
    (re.compile(r"\bfield\s+technician|on[- ]site\b", re.IGNORECASE), "depends on an on-site/field step"),
    (re.compile(r"\bnetwork\s+provisioning\s+delay\b", re.IGNORECASE), "depends on a real-world provisioning delay"),
    (re.compile(r"\bproduction[- ]only\s+access\b", re.IGNORECASE), "depends on production-only access"),
]

_UI_VERBS = re.compile(r"\b(click|tap|fill|navigate|select|login|log in|submit|scroll|hover)\b", re.IGNORECASE)
_API_HINTS = re.compile(r"\b(API|endpoint|REST|GraphQL|POST|GET|PUT|PATCH|response\s+status)\b", re.IGNORECASE)


def _test_case_text(tc: dict) -> str:
    parts: list[str] = [str(tc.get("title") or "")]
    parts.extend(str(p) for p in (tc.get("preconditions") or []))
    for step in tc.get("steps") or []:
        if isinstance(step, dict):
            parts.append(str(step.get("action") or ""))
            parts.append(str(step.get("expected_result") or ""))
        else:
            parts.append(str(step))
    parts.append(str(tc.get("expected_result") or ""))
    return "\n".join(parts)


def _automation_style(text: str) -> str:
    has_ui = bool(_UI_VERBS.search(text))
    has_api = bool(_API_HINTS.search(text))
    if has_ui and has_api:
        return "mixed"
    if has_api and not has_ui:
        return "api"
    return "ui"


def classify_test_case(tc: dict) -> dict:
    """Pure function: one test-case dict -> a verdict dict. No LLM, no I/O —
    easy to test and to re-run cheaply at scale."""
    text = _test_case_text(tc)
    reasons: list[str] = []

    for pattern, reason in _MANUAL_ONLY_PATTERNS:
        if pattern.search(text):
            reasons.append(reason)
    for pattern, reason in _ENVIRONMENT_DEPENDENCY_PATTERNS:
        if pattern.search(text):
            reasons.append(reason)

    if reasons:
        verdict: Verdict = "no"
        reason = "; ".join(reasons)
    elif not text.strip():
        verdict = "unknown"
        reason = "Insufficient test case detail to assess automation eligibility."
    else:
        verdict = "yes"
        reason = "No manual-only or environment-dependency signals detected."

    return {
        "test_case_id": tc.get("test_case_id") or tc.get("id"),
        "verdict": verdict,
        "reason": reason,
        "automation_style": _automation_style(text),
    }


class AutomationEligibilityAgent(BaseAgent):
    """Static-pass automation eligibility classifier — no LLM call."""

    name = "automation_eligibility"

    async def run(self, test_cases: list[dict]) -> AgentRunResult:
        self._logs.clear()
        self.log("info", "start", f"Classifying automation eligibility for {len(test_cases)} test case(s)")

        if not test_cases:
            return AgentRunResult(success=False, error="No test cases provided", data={}, logs=self._logs)

        results = [classify_test_case(tc) for tc in test_cases]
        counts = {"yes": 0, "no": 0, "unknown": 0}
        for r in results:
            counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1

        self.log("info", "complete", f"Eligibility verdicts: {counts}")
        return AgentRunResult(
            success=True,
            data={"results": results, "summary": counts},
            logs=self._logs,
        )

    async def _run(self, input_data: dict) -> dict:
        result = await self.run(test_cases=input_data.get("test_cases", []))
        return result.data
