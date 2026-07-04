"""Runtime preflight: detect which runners can actually execute on this host.

Surfaced to the frontend so users see a clear "Node not installed" rather than
an opaque 500 when they click Run on a Playwright script. The check is cached
for the lifetime of the process; restart the backend after installing tools.
"""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from functools import lru_cache


@dataclass(slots=True)
class FrameworkSupport:
    framework: str
    available: bool
    detail: str  # short human-readable explanation


def _capture_version(args: list[str]) -> str | None:
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return (proc.stdout.strip() or proc.stderr.strip() or "").splitlines()[0] if (proc.stdout or proc.stderr) else None


@lru_cache(maxsize=1)
def _detect_pytest() -> FrameworkSupport:
    if shutil.which("pytest") or shutil.which("py.test"):
        version = _capture_version(["pytest", "--version"]) or ""
        return FrameworkSupport("pytest", True, version or "pytest available")
    # Pytest is in requirements.txt but might be runnable only as `python -m pytest`
    version = _capture_version(["python", "-m", "pytest", "--version"])
    if version is not None:
        return FrameworkSupport("pytest", True, f"python -m pytest ({version})")
    return FrameworkSupport(
        "pytest",
        False,
        "pytest is not on PATH — add it to backend requirements or install it on the host",
    )


@lru_cache(maxsize=1)
def _detect_playwright() -> FrameworkSupport:
    if not shutil.which("npx"):
        return FrameworkSupport(
            "playwright",
            False,
            "npx not found. Install Node.js (LTS) and run `npm install -g @playwright/test` on the host running the backend.",
        )
    version = _capture_version(["npx", "--yes", "playwright", "--version"])
    if not version:
        return FrameworkSupport(
            "playwright",
            False,
            "@playwright/test is not installed. Run `npm install -g @playwright/test && npx playwright install chromium` on the backend host.",
        )
    return FrameworkSupport("playwright", True, version)


def runtime_status() -> dict[str, FrameworkSupport]:
    """One-call summary used by the API and the runners."""
    return {
        "pytest": _detect_pytest(),
        "playwright": _detect_playwright(),
    }


def is_available(framework: str) -> tuple[bool, str]:
    status = runtime_status().get(framework.lower())
    if status is None:
        return False, f"Unsupported framework: {framework}"
    return status.available, status.detail
