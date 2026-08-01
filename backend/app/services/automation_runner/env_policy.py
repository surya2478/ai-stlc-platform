"""Environment allowlist for runner subprocesses (Wave 1, partial AUT-001).

Both local runners build the child environment as `{**os.environ, ...}`, so a
generated or hand-edited test script receives every secret the worker holds:
database URL, LLM provider keys, JWT signing key, Redis credentials. Test code
has no business reading any of them.

This module narrows that to an allowlist. It ships in *audit* mode
(`automation_runner_env_allowlist_enforced=False`): nothing is filtered, but
everything that would be filtered is logged and reported in the runner
metadata, so existing scripts can be checked before the switch is thrown.

The allowlist has two parts. `_ALWAYS_ALLOWED` covers the OS/runtime variables
without which `npx` or `python` simply will not start — stripping PATH does not
harden anything, it just breaks the runner. The configurable part
(`automation_runner_env_allowlist`) covers the test-facing variables scripts
legitimately read.
"""
from __future__ import annotations

import logging
from collections.abc import Mapping

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)


# Runtime/OS essentials. Without these the interpreter or Node launcher fails
# before a single test runs, so they are not negotiable via configuration.
_ALWAYS_ALLOWED: frozenset[str] = frozenset(
    {
        # POSIX
        "PATH",
        "HOME",
        "LANG",
        "LC_ALL",
        "TZ",
        "SHELL",
        "USER",
        "LOGNAME",
        "TMPDIR",
        # Windows
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "APPDATA",
        "LOCALAPPDATA",
        "PROGRAMFILES",
        "PROGRAMFILES(X86)",
        "PROGRAMDATA",
        "USERPROFILE",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
        # Interpreter behaviour the runners set or depend on
        "PYTHONUNBUFFERED",
        "PYTHONIOENCODING",
        "PYTHONPATH",
        "CI",
    }
)


def _matches(name: str, patterns: frozenset[str] | set[str], prefixes: tuple[str, ...]) -> bool:
    return name in patterns or name.startswith(prefixes)


def build_runner_env(
    *,
    source: Mapping[str, str],
    overrides: Mapping[str, str] | None = None,
    settings: Settings | None = None,
    runner_name: str = "runner",
) -> tuple[dict[str, str], list[str]]:
    """Build the environment for a runner subprocess.

    Returns `(env, withheld)` where `withheld` names the variables the policy
    would remove. In audit mode the variables are still present in `env`; the
    caller should surface `withheld` in the run metadata either way so the
    audit trail records what the script could reach.

    `overrides` (AUTOMATION_ENV, CI, …) are applied after filtering and are
    always kept — they are set by the runner itself, not inherited.
    """
    cfg = settings or get_settings()

    configured = set(cfg.automation_runner_env_allowlist_entries)
    prefixes = tuple(entry[:-1] for entry in configured if entry.endswith("*"))
    exact = {entry for entry in configured if not entry.endswith("*")} | set(_ALWAYS_ALLOWED)

    allowed: dict[str, str] = {}
    withheld: list[str] = []
    for key, value in source.items():
        if _matches(key.upper(), exact, prefixes):
            allowed[key] = value
        else:
            withheld.append(key)
    withheld.sort()

    enforced = cfg.automation_runner_env_allowlist_enforced
    env = dict(allowed) if enforced else dict(source)
    if overrides:
        env.update(overrides)

    if withheld:
        logger.warning(
            "%s: %d environment variable(s) %s by the automation runner allowlist: %s",
            runner_name,
            len(withheld),
            "withheld" if enforced else "would be withheld (audit mode)",
            ", ".join(withheld),
        )

    return env, withheld
