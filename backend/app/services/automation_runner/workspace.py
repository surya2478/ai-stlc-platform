"""Per-run workspace management.

Each automation execution gets its own directory under
  <file_storage_path>/automation_workspace/<execution_run_id>/

The script source code from AutomationScript.code is written into it, framework
config (package.json / playwright.config.ts) is generated when needed, and the
runner places artifacts (log.txt, screenshots, traces) under the same directory
so the API can stream them back through one authenticated endpoint.
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from app.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()


# ── Workspace layout ────────────────────────────────────────────────────────

def workspace_root() -> Path:
    return Path(settings.file_storage_path) / "automation_workspace"


def workspace_dir_for_run(run_id: int | str) -> Path:
    return workspace_root() / str(run_id)


def reset_workspace(run_id: int | str) -> Path:
    """Wipe + recreate the workspace dir. Idempotent for retries.

    Accepts a plain run id for single-script runs, or a composite string key
    (e.g. "{run_id}-{script_id}") for batch runs where several scripts share
    one ExecutionRun and need isolated workspace directories.
    """
    path = workspace_dir_for_run(run_id)
    if path.exists():
        shutil.rmtree(path, ignore_errors=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


# ── Script materialisation ───────────────────────────────────────────────────

def _script_filename_for(framework: str, suggested_path: str | None) -> str:
    """Pick a filename inside the workspace. Honours the LLM's suggestion when
    it's a sensible single-file name, otherwise picks a canonical default."""
    fw = (framework or "").lower()
    # Strip any directory components the LLM may have included.
    candidate = Path(suggested_path or "").name if suggested_path else ""
    if candidate and "/" not in candidate and "\\" not in candidate:
        # Coerce extension to match framework if mismatched
        if fw == "playwright" and not candidate.endswith((".ts", ".js", ".spec.ts", ".spec.js")):
            candidate = ""
        if fw == "pytest" and not candidate.endswith(".py"):
            candidate = ""
    if not candidate:
        if fw == "playwright":
            candidate = "test.spec.ts"
        elif fw == "pytest":
            candidate = "test_script.py"
        else:
            candidate = "script.txt"
    if fw == "pytest" and not candidate.startswith("test_"):
        # Pytest auto-discovery only picks files named test_*.py
        candidate = f"test_{candidate}"
    return candidate


def materialize_script(
    *,
    workspace: Path,
    framework: str,
    code: str,
    suggested_file_path: str | None,
) -> str:
    """Write the script source to disk and return its filename."""
    filename = _script_filename_for(framework, suggested_file_path)
    (workspace / filename).write_text(code, encoding="utf-8")
    return filename


def materialize_bundle(*, workspace: Path, compiled_files: dict[str, str]) -> None:
    """Write every file in a Script Compiler bundle (Phase 2) into the
    workspace, creating subdirectories (specs/pages/fixtures/utils) as
    needed. Use `AutomationScript.file_path` as the entry path passed to
    `run_script_for_execution` — this only materialises the tree.

    Defense in depth: `compiled_files` keys are expected to already be safe
    relative paths (the Script Compiler validates/derives them from
    contract fields), but a containment check is enforced here too so a
    malformed or future-untrusted key (e.g. "../../etc/x") can never write
    outside `workspace`, matching the same guard `_lift_attachments` in
    `local_playwright.py` applies on the read side.
    """
    workspace = workspace.resolve()
    for relative_path, content in compiled_files.items():
        target = (workspace / relative_path).resolve()
        if target != workspace and workspace not in target.parents:
            raise ValueError(f"Refusing to write outside workspace: {relative_path!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


# ── Framework-specific scaffolding ───────────────────────────────────────────

# Exact, not a caret range. The platform itself never installs this — the
# workspace's node_modules is symlinked to the npm global root below — so the
# version here is what a *downloaded* bundle resolves when someone runs
# `npm install` outside the platform. `^1.44.0` let that resolve to whatever
# the newest 1.x happened to be, which by 1.62 was four releases of removed
# APIs away from what the platform actually ran the tests on. Keep this equal
# to the `npm install -g` line in backend/Dockerfile.
PLAYWRIGHT_PACKAGE_JSON = {
    "name": "stlc-automation-run",
    "private": True,
    "version": "0.0.0",
    "devDependencies": {
        "@playwright/test": "1.62.1",
    },
    "scripts": {
        "test": "playwright test",
    },
}

# Captures trace + video on first retry, screenshot on every failure. The JSON
# reporter dumps to results.json which the runner parses for per-test outcomes.
# {base_url_line} expands to either an empty string or `    baseURL: '...',`
# depending on whether the caller resolved a target URL for the run.
# {test_dir} is '.' for a legacy single-file script, or 'specs' for a Phase 2
# compiled bundle (specs/pages/fixtures/utils tree).
PLAYWRIGHT_CONFIG_TS_TEMPLATE = """import {{ defineConfig }} from '@playwright/test';

export default defineConfig({{
  testDir: '{test_dir}',
  fullyParallel: false,
  retries: 0,
  workers: 1,
  // Playwright's default per-test timeout is 30s — empirically too tight for
  // LLM-authored multi-step flows against slow SIT environments plus
  // cold-start Docker runner containers (every non-locator Studio batch
  // failure observed live on 2026-07-11 was "Test timeout of 30000ms
  // exceeded"). The runner's own subprocess hard cap still bounds the run.
  timeout: 90_000,
  reporter: [
    ['list'],
    ['json', {{ outputFile: 'results.json' }}],
  ],
  use: {{
{base_url_line}    headless: true,
    locale: 'en-US',
    timezoneId: 'America/New_York',
    storageState: 'storageState.json',
    actionTimeout: 15_000,
    navigationTimeout: 30_000,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  }},
  expect: {{ timeout: 10_000 }},
}});
"""


def google_locale_cookie(target_url: str | None) -> dict | None:
    """PREF=hl=en forces Google's UI to render in English regardless of the
    request's geographic locale (e.g. google.ae defaults to Arabic without
    it) — locators grounded against an English-rendered page become
    unreliable otherwise. Only applies when target_url's host actually is a
    google.<tld> domain, matched dynamically instead of a hardcoded
    .google.com, so it also covers google.ae, google.co.uk, etc. Shared by
    both the crawler (planner_agent) and the test runner (this module) so
    the locale forced during discovery matches what's forced at execution.
    """
    host = (urlparse(target_url).hostname or "").lower() if target_url else ""
    labels = host.split(".")
    if "google" not in labels:
        return None
    registrable_domain = ".".join(labels[labels.index("google"):])
    return {
        "name": "PREF",
        "value": "hl=en",
        "domain": f".{registrable_domain}",
        "path": "/",
        "expires": 1800000000,
        "httpOnly": False,
        "secure": True,
        "sameSite": "Lax",
    }


def _render_playwright_config(base_url: str | None, test_dir: str) -> str:
    """Build the playwright.config.ts source, injecting baseURL when supplied."""
    if base_url:
        # JSON-encoding gives us a safely quoted string we can embed in TS.
        escaped = json.dumps(base_url)
        base_url_line = f"    baseURL: {escaped},\n"
    else:
        base_url_line = ""
    return PLAYWRIGHT_CONFIG_TS_TEMPLATE.format(base_url_line=base_url_line, test_dir=test_dir)


def write_playwright_config(workspace: Path, base_url: str | None = None, test_dir: str = ".") -> None:
    """Drop package.json + playwright.config.ts and make @playwright/test
    resolvable from the workspace.

    Node only walks up looking for `node_modules` — it does not consult the
    global install path automatically. So when `@playwright/test` lives at
    /usr/lib/node_modules (npm global), we symlink the workspace's
    `node_modules` directory to it. After that, `import { … } from '@playwright/test'`
    in playwright.config.ts and the spec file resolves the same way it would
    in a `npm install`-ed local project.

    When `base_url` is provided, it's injected as Playwright's `use.baseURL`
    so generated specs can use relative paths like `page.goto('/')`. Pass
    `test_dir="specs"` for a Phase 2 compiled bundle (specs/pages/fixtures/
    utils tree); the default `"."` matches a legacy single-file script.
    """
    (workspace / "package.json").write_text(
        json.dumps(PLAYWRIGHT_PACKAGE_JSON, indent=2), encoding="utf-8"
    )
    cookie = google_locale_cookie(base_url)
    storage_state = {
        "cookies": [cookie] if cookie else [],
        "origins": []
    }
    (workspace / "storageState.json").write_text(
        json.dumps(storage_state, indent=2), encoding="utf-8"
    )
    (workspace / "playwright.config.ts").write_text(
        _render_playwright_config(base_url, test_dir), encoding="utf-8"
    )
    _link_npm_global_modules(workspace)


@lru_cache(maxsize=1)
def _npm_global_root() -> str | None:
    """Return the npm global modules directory (e.g. /usr/lib/node_modules).

    Cached for the process lifetime; restart the worker after a Node reinstall.
    """
    try:
        proc = subprocess.run(
            ["npm", "root", "-g"], capture_output=True, text=True, timeout=10
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        logger.warning("npm not found while resolving global module root")
        return None
    if proc.returncode != 0:
        logger.warning("npm root -g failed: %s", proc.stderr.strip())
        return None
    return proc.stdout.strip() or None


def _link_npm_global_modules(workspace: Path) -> None:
    """Create workspace/node_modules → npm global root so Node finds @playwright/test."""
    link = workspace / "node_modules"
    # Replace stale links from a previous failed run
    if link.is_symlink() or link.exists():
        try:
            if link.is_symlink() or link.is_file():
                link.unlink()
            else:
                shutil.rmtree(link, ignore_errors=True)
        except OSError:
            pass
    target = _npm_global_root()
    if not target:
        return
    target_path = Path(target)
    if not target_path.exists():
        logger.warning("npm global root %s does not exist; @playwright/test may not resolve", target)
        return
    try:
        link.symlink_to(target_path, target_is_directory=True)
    except OSError as exc:
        # Filesystem may not support symlinks (rare on Linux containers);
        # fall back to a directory copy as a last resort.
        logger.warning("Could not symlink %s -> %s (%s); falling back to copy", link, target_path, exc)
        try:
            shutil.copytree(target_path, link, symlinks=True, dirs_exist_ok=False)
        except OSError as copy_exc:
            logger.warning("Copy fallback also failed: %s", copy_exc)


def write_pytest_config(workspace: Path) -> None:
    """Pytest needs no config for a single-file run. Drop a stub conftest.py to
    keep auto-discovery scoped to this workspace dir."""
    (workspace / "conftest.py").write_text("", encoding="utf-8")
