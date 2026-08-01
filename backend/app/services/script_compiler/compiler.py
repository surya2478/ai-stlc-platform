"""
Script Compiler (Phase 2.2/2.3) — Automation Generation Contract -> a
deterministic, versioned file bundle. This is the only thing that renders
runnable code; agents never persist code directly (see ADR-001).

The static utility files (apiClient.ts, dbValidator.ts, evidenceHelper.ts,
db_validator.py) are read verbatim from the golden sample set
(golden_samples/) rather than duplicated here — the golden samples ARE the
compiler's boilerplate output, by construction, not just a separate
reference document.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from app.agents.automation.generation_contract import AutomationGenerationContract
from app.services.script_compiler import playwright_renderer, pytest_renderer
from app.services.script_compiler.naming import slugify

COMPILER_VERSION = "1.0.0"
SUPPORTED_CONTRACT_VERSIONS = {"1.0"}

_GOLDEN_DIR = Path(__file__).parent / "golden_samples"
_GOLDEN_PLAYWRIGHT_UTILS_DIR = _GOLDEN_DIR / "playwright" / "utils"
_GOLDEN_PYTEST_UTILS_DIR = _GOLDEN_DIR / "pytest" / "utils"


class UnsupportedContractVersionError(ValueError):
    """Raised when a contract declares a contractVersion this compiler build
    cannot render. The compiler is required to support version N and N-1;
    anything older must be migrated forward before it can compile again."""


@dataclass
class CompiledBundle:
    files: dict[str, str] = field(default_factory=dict)  # relative path -> content
    entry_path: str = ""  # the main spec/test file's path within `files`
    setup_required: list[str] = field(default_factory=list)
    execution_command: str = ""
    compiler_version: str = COMPILER_VERSION
    contract_version: str = "1.0"


def _read_golden_util(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compile_playwright(contract: AutomationGenerationContract) -> CompiledBundle:
    slug = slugify(contract.test_case_id, contract.business_flow)
    spec_path = f"specs/{slug}.spec.ts"

    files: dict[str, str] = {
        spec_path: playwright_renderer.render_spec(contract, compiler_version=COMPILER_VERSION),
    }
    for page_object in contract.page_objects:
        files[f"pages/{page_object.name}.ts"] = playwright_renderer.render_page_object(page_object)
    if contract.test_data_bindings:
        files["fixtures/testData.fixture.ts"] = playwright_renderer.render_fixture(contract)
    # api_call cleanup actions render getJson too, so the helper has to ship
    # whenever either one is present — not just for apiValidations.
    needs_api_client = bool(contract.api_validations) or any(
        c.type == "api_call" and c.target for c in contract.cleanup_actions
    )
    if needs_api_client:
        files["utils/apiClient.ts"] = _read_golden_util(_GOLDEN_PLAYWRIGHT_UTILS_DIR / "apiClient.ts")
    if contract.db_validations:
        files["utils/dbValidator.ts"] = _read_golden_util(_GOLDEN_PLAYWRIGHT_UTILS_DIR / "dbValidator.ts")
    if contract.evidence_required:
        files["utils/evidenceHelper.ts"] = _read_golden_util(_GOLDEN_PLAYWRIGHT_UTILS_DIR / "evidenceHelper.ts")

    return CompiledBundle(
        files=files,
        entry_path=spec_path,
        setup_required=["npm install @playwright/test", "npx playwright install"],
        execution_command=f"npx playwright test {spec_path}",
        compiler_version=COMPILER_VERSION,
        contract_version=contract.contract_version,
    )


def _compile_pytest(contract: AutomationGenerationContract) -> CompiledBundle:
    slug = slugify(contract.test_case_id, contract.business_flow)
    test_path = f"test_{slug}.py"

    files: dict[str, str] = {
        test_path: pytest_renderer.render_test_module(contract, compiler_version=COMPILER_VERSION),
    }
    if contract.db_validations:
        # Flat, sibling module — matches automation_runner's existing flat
        # pytest workspace convention (no package, rootdir-based collection).
        files["db_validator.py"] = _read_golden_util(_GOLDEN_PYTEST_UTILS_DIR / "db_validator.py")

    setup = ["pip install pytest httpx"]
    if any(
        s.action in ("fill", "click", "check", "uncheck", "select", "hover", "wait_for_visible")
        for s in contract.steps
    ):
        setup.append("pip install playwright pytest-playwright")

    return CompiledBundle(
        files=files,
        entry_path=test_path,
        setup_required=setup,
        execution_command=f"pytest {test_path} -v",
        compiler_version=COMPILER_VERSION,
        contract_version=contract.contract_version,
    )


def compile_contract(contract: AutomationGenerationContract) -> CompiledBundle:
    """Compile a validated Automation Generation Contract into a
    deterministic file bundle. Two identical contracts (differing only in
    page objects/steps) always produce structurally identical output."""
    if contract.contract_version not in SUPPORTED_CONTRACT_VERSIONS:
        raise UnsupportedContractVersionError(
            f"Script Compiler {COMPILER_VERSION} does not support contract version "
            f"'{contract.contract_version}' (supported: {sorted(SUPPORTED_CONTRACT_VERSIONS)})"
        )
    if contract.script_type == "pytest-python":
        return _compile_pytest(contract)
    return _compile_playwright(contract)
