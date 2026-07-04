"""AI-assisted manual execution.

A tester clicks "Ask AI" on a manual step. We call the configured LLM with:
  - the step's action and expected_result text (already substituted for ${vars})
  - the tester's actual_result and comments
  - optionally a screenshot (used when a vision-capable model is configured)

The LLM returns a structured suggestion (pass / fail / blocked + confidence +
reasoning). The tester explicitly applies or dismisses it — we never auto-apply,
so the tester is always the system of record. The suggestion is also stored on
the step's metadata for audit.

Cost: one LLM call per click. The tester drives invocation (no auto-suggest on
typing) so cost is predictable.
"""
from __future__ import annotations

import base64
import logging

from app.agents.structured_schemas import AiAssistSuggestion
from app.config import get_settings
from app.llm.provider import LLMCircuitOpenError, get_llm, validate_vision_configuration
from app.llm.structured import parse_and_validate_llm_output
from app.models.execution import ManualStepResult

logger = logging.getLogger(__name__)
settings = get_settings()


class AiAssistUnavailable(Exception):
    """Raised when the LLM is unreachable / circuit-open / out of quota.

    The endpoint catches this and returns a friendly 'blocked + decide manually'
    suggestion instead of a 500.
    """


_SYSTEM_PROMPT = """You are an experienced QA reviewer helping a manual tester
decide whether a single test step has passed, failed, or is blocked.

You will receive:
  - the step's intended action,
  - the expected result,
  - the tester's observed (actual) result, optionally with their comments,
  - optionally a screenshot of the application's current state.

Decide:
  suggested_status: one of "pass" | "fail" | "blocked"
  confidence: an integer 0-100 reflecting how sure you are
  reasoning: 1-2 sentences explaining the decision in tester-friendly language
  observations: up to 4 short bullet points noting concrete details
                that influenced the decision (what you saw on screen,
                discrepancies, missing elements, etc.)

Rules:
  - "pass" only when the actual result clearly matches the expected result.
  - "fail" when the actual result clearly contradicts the expected result.
  - "blocked" when you cannot tell (insufficient evidence, screenshot unclear,
    tester didn't fill in actual_result). Be honest — low confidence + "blocked"
    is better than a confident wrong guess.
  - Never invent evidence. If the screenshot shows something the tester didn't
    mention, surface it in observations rather than treating it as fact.
  - Output ONLY a JSON object — no markdown, no commentary."""


def _build_user_text(
    *,
    action: str | None,
    expected: str | None,
    actual: str | None,
    comments: str | None,
    has_screenshot: bool,
) -> str:
    parts = [
        f"STEP ACTION:\n{action or '(none provided)'}",
        f"\nEXPECTED RESULT:\n{expected or '(none provided)'}",
        f"\nACTUAL RESULT (typed by tester):\n{actual or '(empty)'}",
    ]
    if comments:
        parts.append(f"\nTESTER COMMENTS:\n{comments}")
    parts.append(
        f"\nSCREENSHOT: {'attached — review it carefully' if has_screenshot else 'not attached'}"
    )
    parts.append(
        "\nReturn a JSON object: "
        '{"suggested_status": "pass"|"fail"|"blocked", '
        '"confidence": 0-100, "reasoning": "...", '
        '"observations": ["...", "..."]}'
    )
    return "\n".join(parts)


async def suggest_step_outcome(
    step: ManualStepResult,
    *,
    actual_result_override: str | None = None,
    comments_override: str | None = None,
    screenshot_bytes: bytes | None = None,
) -> dict:
    """Ask the configured LLM whether `step` looks like pass / fail / blocked.

    Returns a dict shaped like AiAssistSuggestion, plus an `inputs_used` block
    describing what the model saw (helpful for the audit trail). Falls back to
    text-only when a screenshot is supplied but vision isn't configured.
    """
    actual = actual_result_override if actual_result_override is not None else step.actual_result
    comments = comments_override if comments_override is not None else step.comments

    vision_blocker: str | None = None
    if screenshot_bytes:
        vision_blocker = validate_vision_configuration()
        if vision_blocker:
            logger.info("AI assist: screenshot provided but vision unavailable — falling back to text. Reason: %s", vision_blocker)

    use_vision = bool(screenshot_bytes) and not vision_blocker
    user_text = _build_user_text(
        action=step.action_text,
        expected=step.expected_text,
        actual=actual,
        comments=comments,
        has_screenshot=use_vision,
    )

    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)

    try:
        if use_vision:
            vision_llm = get_llm(settings.default_llm_provider, settings.default_vision_model)
            b64 = base64.b64encode(screenshot_bytes).decode("ascii")
            response_text = await vision_llm.generate_vision(
                system=_SYSTEM_PROMPT,
                user=user_text,
                images_b64=[b64],
            )
        else:
            response_text = await llm.achat(
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user_text},
                ]
            )
    except LLMCircuitOpenError as exc:
        logger.warning("AI assist: LLM circuit open: %s", exc)
        raise AiAssistUnavailable(
            "AI is temporarily unavailable (circuit breaker open). Try again in a minute."
        )
    except Exception as exc:
        logger.warning("AI assist: LLM call failed: %s", exc)
        raise AiAssistUnavailable(
            "AI is unavailable right now. Please decide this step manually."
        )

    try:
        suggestion = parse_and_validate_llm_output(response_text, AiAssistSuggestion)
    except ValueError as exc:
        logger.warning("AI assist response failed schema validation: %s", exc)
        return {
            "suggested_status": "blocked",
            "confidence": 0,
            "reasoning": "The AI returned an unparseable response. Decide manually.",
            "observations": [],
            "inputs_used": _inputs_used(use_vision, vision_blocker),
            "raw_response": response_text[:2000] if isinstance(response_text, str) else None,
        }

    result = suggestion.model_dump(mode="json")
    result["inputs_used"] = _inputs_used(use_vision, vision_blocker)
    return result


def _inputs_used(use_vision: bool, vision_blocker: str | None) -> dict:
    return {
        "mode": "vision" if use_vision else "text_only",
        "vision_blocker": vision_blocker,
    }
