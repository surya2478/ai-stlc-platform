"""
Agent 7 — Automation Script Agent
Generates Playwright / Pytest automation scripts from approved test cases.
"""
import json
import logging
import re
from typing import Any, TypedDict

from langgraph.graph import StateGraph, END

from app.agents.base.base_agent import BaseAgent, AgentResult
from app.agents.structured_schemas import AutomationScriptLLMOutput
from app.llm.provider import get_llm
from app.llm.structured import validate_structured_output, clean_json_text
from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


# ── State ──────────────────────────────────────────────────────────────────────

class AutomationState(TypedDict):
    test_cases: list[dict]
    framework: str
    scripts: list[dict]
    errors: list[str]


# ── Prompts ───────────────────────────────────────────────────────────────────

PLAYWRIGHT_SYSTEM = """You are a senior automation engineer specialising in Playwright (TypeScript).

For each test case, generate a complete, runnable Playwright test. Each script object must contain:
- test_case_id: the source test case ID (e.g. "TC-0001")
- framework: "playwright"
- file_path: suggested file path (e.g. "tests/login/tc_0001_valid_login.spec.ts")
- code: complete TypeScript Playwright test code including imports, describe block, and test steps
- setup_required: list of setup commands (e.g. ["npm install @playwright/test", "npx playwright install"])
- execution_command: how to run this specific test (e.g. "npx playwright test tests/login/tc_0001_valid_login.spec.ts")

The code must:
1. Use @playwright/test framework
2. Follow the test steps from the test case exactly
3. Include proper selectors (use data-testid when possible)
4. Add meaningful assertions after each action
5. Handle async/await properly
6. Include page object pattern where appropriate
7. NEVER invent a placeholder domain (e.g. example.com, yoursite.com). If the
   test case context has has_configured_base_url=true, navigate using ONLY
   relative paths — page.goto('/relative/path') — Playwright's configured
   baseURL will resolve them against the real application URL at run time. If
   has_configured_base_url is false, use page.goto('/') and add a comment
   noting that a real base URL must be configured for this application before
   the test can pass.
8. If external_dependencies are listed in the context, do NOT navigate to or
   call those services live. Use page.route('**/*pattern*', handler) to
   intercept and mock them, or add a clear TODO comment stubbing that portion
   of the flow if a pattern can't be inferred confidently.

Output ONLY a valid JSON array of script objects. No extra text.
"""

PYTEST_SYSTEM = """You are a senior automation engineer specialising in Pytest and Python.

For each test case, generate a complete, runnable Pytest test. Each script object must contain:
- test_case_id: the source test case ID (e.g. "TC-0001")
- framework: "pytest"
- file_path: suggested file path (e.g. "tests/test_login.py")
- code: complete Python pytest code with fixtures, test function, and assertions
- setup_required: list of pip packages (e.g. ["pytest", "pytest-asyncio", "httpx"])
- execution_command: how to run this test (e.g. "pytest tests/test_login.py::test_valid_login -v")

The code must:
1. Use pytest fixtures for setup/teardown
2. Follow the BDD scenario if provided (use pytest-bdd or plain steps)
3. Include proper assertions using assert statements
4. Use httpx or requests for API tests, selenium/playwright for UI tests
5. Include docstrings explaining the test
6. NEVER invent a placeholder domain (e.g. example.com, yoursite.com). Build
   all URLs from a `BASE_URL` value read from an environment variable /
   fixture (e.g. `os.environ["BASE_URL"]`) rather than hardcoding a host. If
   has_configured_base_url is false in the test case context, add a comment
   noting a real BASE_URL must be configured before the test can pass.
7. If external_dependencies are listed in the context, do NOT call those
   services live. Mock them (e.g. via `responses`/`httpx` mocking/monkeypatch)
   rather than making real network calls to third parties.

Output ONLY a valid JSON array of script objects. No extra text.
"""


# ── Nodes ──────────────────────────────────────────────────────────────────────

def _repair_json(text: str) -> str:
    """
    Best-effort repair of LLM JSON that contains unescaped control characters
    (literal newlines/tabs inside string values).
    Strategy: find string values and escape any raw control chars inside them.
    """
    result = []
    in_string = False
    escape_next = False
    for ch in text:
        if escape_next:
            result.append(ch)
            escape_next = False
            continue
        if ch == '\\' and in_string:
            result.append(ch)
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            result.append(ch)
            continue
        if in_string:
            # Escape control characters that are illegal in JSON strings
            if ch == '\n':
                result.append('\\n')
            elif ch == '\r':
                result.append('\\r')
            elif ch == '\t':
                result.append('\\t')
            elif ord(ch) < 0x20:
                result.append(f'\\u{ord(ch):04x}')
            else:
                result.append(ch)
        else:
            result.append(ch)
    return ''.join(result)


def _parse_script_response(text: str, framework: str) -> tuple[dict | None, str | None]:
    """Parse a single script object from LLM response. Returns (script_dict, error)."""
    clean = re.sub(r'```(?:json|typescript|python|js)?\s*', '', text)
    clean = clean.replace('```', '').strip()

    def _try_parse(s: str) -> dict | list | None:
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            try:
                return json.loads(_repair_json(s))
            except json.JSONDecodeError:
                return None

    def _parse_loose_script_object(s: str) -> dict | None:
        """
        Recover common LLM output where the `code` value is emitted as a raw
        multiline string with unescaped quotes inside the code body.
        """
        start = s.find("{")
        end = s.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None

        obj = s[start:end + 1]
        code_match = re.search(r'"code"\s*:\s*"', obj)
        if not code_match:
            return None

        code_start = code_match.end()
        tail = obj[code_start:]
        next_field = re.search(r'"\s*,\s*"setup_required"\s*:', tail)
        if not next_field:
            return None

        code = tail[:next_field.start()].strip()
        safe_obj = (
            obj[:code_match.start()]
            + '"code": "__CODE_PLACEHOLDER__", "setup_required":'
            + tail[next_field.end():]
        )
        parsed = _try_parse(safe_obj)
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else None
        if not isinstance(parsed, dict):
            return None

        parsed["code"] = code
        return parsed

    # Try full parse first
    parsed = _try_parse(clean)
    if parsed is not None:
        if isinstance(parsed, list) and parsed:
            return parsed[0], None
        if isinstance(parsed, dict):
            return parsed, None

    loose = _parse_loose_script_object(clean)
    if loose is not None:
        return loose, None

    # Find first {...} object
    cleaned_obj = clean_json_text(clean)
    if cleaned_obj.startswith("{"):
        parsed = _try_parse(cleaned_obj)
        if parsed is not None:
            return (parsed[0] if isinstance(parsed, list) else parsed), None
        loose = _parse_loose_script_object(cleaned_obj)
        if loose is not None:
            return loose, None
        return None, f"JSON parse error even after repair. Snippet: {text[:200]}"

    return None, f"No JSON object found in response (first 200 chars): {text[:200]}"


async def _generate_scripts(state: AutomationState) -> AutomationState:
    """Generate one script per test case to avoid token-limit issues."""
    llm = get_llm(settings.default_llm_provider, settings.default_llm_model)
    errors = []
    framework = state["framework"]
    system = PLAYWRIGHT_SYSTEM if framework == "playwright" else PYTEST_SYSTEM
    scripts = []

    for tc in state["test_cases"]:
        tc_summary = {
            "test_case_id": tc.get("test_case_id", str(tc.get("id", ""))),
            "title": tc.get("title"),
            "preconditions": tc.get("preconditions", []),
            "steps": tc.get("steps", []),
            "expected_result": tc.get("expected_result"),
            "bdd_scenario": tc.get("bdd_scenario"),
            "test_type": tc.get("test_type"),
            "application_name": tc.get("application_name"),
            "has_configured_base_url": tc.get("has_configured_base_url", False),
            "external_dependencies": tc.get("external_dependencies", []),
        }
        prompt = f"""Generate a single {framework} automation script for this test case:

{json.dumps(tc_summary, indent=2)}

Return a single JSON object (not an array) with: test_case_id, framework, file_path, code, setup_required, execution_command."""

        try:
            response = await llm.achat(
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": prompt},
                ]
            )
            text = response.strip()
            logger.info("Automation LLM response for %s: %d chars", tc_summary["test_case_id"], len(text))

            script, err = _parse_script_response(text, framework)
            if script:
                if not script.get("test_case_id"):
                    script["test_case_id"] = tc_summary["test_case_id"]
                scripts.append(script)
            else:
                errors.append(f"Failed to parse script for {tc_summary['test_case_id']}: {err}")
                logger.error("Script parse failed for %s: %s\nRaw: %s", tc_summary["test_case_id"], err, text[:300])
        except Exception as exc:
            exc_str = str(exc)
            if "rate_limit_exceeded" in exc_str or "429" in exc_str:
                # Extract wait time hint from error message if available
                wait_match = re.search(r'try again in ([\d.]+[smh])', exc_str)
                wait_hint = f" Please try again in {wait_match.group(1)}." if wait_match else " Daily token quota may be exhausted — try again later."
                msg = f"Groq rate limit hit for {tc_summary['test_case_id']}.{wait_hint}"
                errors.append(msg)
                logger.warning(msg)
                # Stop processing remaining test cases — quota is exhausted
                break
            else:
                errors.append(f"LLM error for {tc_summary['test_case_id']}: {exc_str}")
                logger.exception("LLM call failed for %s", tc_summary["test_case_id"])

    logger.info("Automation agent: generated %d/%d scripts", len(scripts), len(state["test_cases"]))
    return {**state, "scripts": scripts, "errors": errors}


def _validate_scripts(state: AutomationState) -> AutomationState:
    """Ensure required fields present in each script."""
    validated = []
    errors = list(state["errors"])
    for s in state["scripts"]:
        try:
            s = validate_structured_output(s, AutomationScriptLLMOutput).model_dump(mode="json")
        except Exception as exc:
            errors.append(f"Automation script schema validation failed: {exc}")
            continue
        if not s.get("code"):
            s["code"] = "# TODO: implement test\nimport pytest\n\ndef test_placeholder():\n    pass"
        if not s.get("framework"):
            s["framework"] = state["framework"]
        if not s.get("setup_required"):
            s["setup_required"] = (
                ["npm install @playwright/test", "npx playwright install"]
                if state["framework"] == "playwright"
                else ["pip install pytest pytest-asyncio httpx"]
            )
        validated.append(s)
    return {**state, "scripts": validated, "errors": errors}


# ── Graph ──────────────────────────────────────────────────────────────────────

def _build_graph() -> Any:
    graph = StateGraph(AutomationState)
    graph.add_node("generate", _generate_scripts)
    graph.add_node("validate", _validate_scripts)
    graph.set_entry_point("generate")
    graph.add_edge("generate", "validate")
    graph.add_edge("validate", END)
    return graph.compile()


_graph = _build_graph()

# ── Agent Class ────────────────────────────────────────────────────────────────

class AutomationAgentResult:
    def __init__(self, success: bool, data: dict, logs: list, error: str | None = None):
        self.success = success
        self.data = data
        self.logs = logs
        self.error = error


class AutomationScriptAgent:
    """Agent 7 — wraps the LangGraph automation pipeline."""

    async def run(self, test_cases: list[dict], framework: str = "playwright") -> AutomationAgentResult:
        logs: list[dict] = []
        try:
            initial_state: AutomationState = {
                "test_cases": test_cases,
                "framework": framework,
                "scripts": [],
                "errors": [],
            }
            final_state = await _graph.ainvoke(initial_state)
            scripts = final_state.get("scripts", [])
            errors = final_state.get("errors", [])

            for err in errors:
                logs.append({"level": "warning", "message": err})

            logger.info("AutomationScriptAgent finished: %d scripts, %d errors", len(scripts), len(errors))
            return AutomationAgentResult(
                success=True,
                data={"scripts": scripts},
                logs=logs,
            )
        except Exception as exc:
            logger.exception("AutomationScriptAgent crashed")
            return AutomationAgentResult(
                success=False,
                data={"scripts": []},
                logs=logs,
                error=str(exc),
            )
