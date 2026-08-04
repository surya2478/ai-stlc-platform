"""Server-owned runner mode policy (Wave 1 / P0-01).

Before this module the runner mode was whatever the caller happened to pass,
and every caller that passed nothing silently got the *least* isolated runner:
`get_runner_for_framework` falls back to the local subprocess map when
`runner_mode` is None. The governed paths — asset dry runs and suite command
center execution — were exactly the ones omitting it.

The rule now: callers may express a *preference*, the server decides. A mode
that policy refuses does not quietly downgrade to something else; it produces a
typed refusal that the caller turns into a blocked/automation-failure result.
Failing closed is the point — a refusal is visible, a silent downgrade is not.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.config import Settings, get_settings

VALID_MODES = ("local", "docker", "executor")

# Where the Docker API lives when "docker" mode drives it directly. Only
# containers that mount it can run in that mode; in this deployment that is
# the runner-executor service and deliberately NOT the worker.
DOCKER_SOCKET_PATH = "/var/run/docker.sock"


def _docker_socket_available(path: str = DOCKER_SOCKET_PATH) -> bool:
    """Whether this process can actually reach the Docker daemon.

    Existence, not connectivity: a socket that exists but refuses a
    connection is a different failure, and one worth surfacing from the run
    itself rather than guessing about here.
    """
    return os.path.exists(path)


@dataclass(frozen=True, slots=True)
class RunnerPolicyDecision:
    """What the server decided, and enough context to explain it in the UI."""

    mode: str
    requested: str | None
    permitted: bool
    reason: str | None = None

    def as_metadata(self) -> dict:
        return {
            "runner_mode": self.mode,
            "runner_mode_requested": self.requested,
            "runner_policy_permitted": self.permitted,
        }


def resolve_runner_mode(
    requested: str | None = None,
    *,
    settings: Settings | None = None,
) -> RunnerPolicyDecision:
    """Decide the effective runner mode for one execution.

    `requested` is a preference (e.g. a Studio batch config). When it is absent
    or unrecognised the configured server default applies.
    """
    cfg = settings or get_settings()

    normalized = (requested or "").strip().lower() or None
    if normalized is not None and normalized not in VALID_MODES:
        # An unknown mode is a caller bug, not a licence to pick for them.
        return RunnerPolicyDecision(
            mode=normalized,
            requested=requested,
            permitted=False,
            reason=(
                f"Unknown runner mode '{requested}'. "
                f"Supported modes: {', '.join(VALID_MODES)}."
            ),
        )

    effective = normalized or cfg.automation_runner_mode

    if effective == "local" and not cfg.local_runner_permitted:
        return RunnerPolicyDecision(
            mode=effective,
            requested=requested,
            permitted=False,
            reason=(
                "Local runner execution is not permitted in this deployment "
                f"(app_env='{cfg.app_env}'). Local mode runs test code inside the "
                "worker process with the worker's own credentials. Configure "
                "AUTOMATION_RUNNER_MODE=docker, or set "
                "AUTOMATION_ALLOW_LOCAL_RUNNER=true to accept that risk explicitly."
            ),
        )

    if effective == "executor" and not (
        cfg.automation_executor_url and cfg.automation_executor_token
    ):
        # Falling back to a lesser mode here would silently undo the isolation
        # the operator asked for, which is the failure this module exists to
        # prevent.
        return RunnerPolicyDecision(
            mode=effective,
            requested=requested,
            permitted=False,
            reason=(
                "Runner mode 'executor' requires both AUTOMATION_EXECUTOR_URL and "
                "AUTOMATION_EXECUTOR_TOKEN to be configured."
            ),
        )

    if effective == "docker" and not _docker_socket_available():
        # The one gap in an otherwise closed gate: "local" was refused without
        # permission and "executor" without a URL and token, but "docker" was
        # permitted without ever checking the thing it drives. A Studio run
        # whose Step 1 dropdown said "docker" therefore reached the worker,
        # which does not mount the socket, and failed every test with "docker
        # daemon not reachable". Observed live 2026-08-03: five tests, no
        # browser ever started, and the failure surfaced as an application
        # problem rather than a configuration one.
        return RunnerPolicyDecision(
            mode=effective,
            requested=requested,
            permitted=False,
            reason=(
                f"Runner mode 'docker' drives the Docker daemon directly, but {DOCKER_SOCKET_PATH} "
                "is not mounted into this service — so no container can be started. Use "
                "'executor', which runs the tests in the isolated runner-executor service that "
                "does hold the socket, or mount the socket into this one."
            ),
        )

    return RunnerPolicyDecision(mode=effective, requested=requested, permitted=True)
