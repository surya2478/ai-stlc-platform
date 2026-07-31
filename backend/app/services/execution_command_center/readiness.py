"""The five-way readiness gate — a hard precondition before a suite run starts.

The tracker's P1-S7 checklist requires environment, application, data, framework
and worker readiness before execution begins. This module resolves those five
axes for a published snapshot and returns one structured verdict.

It does not reimplement the individual probes. `automation_runner/readiness.py`
already owns the environment, application, data and framework checks and is
reused verbatim; the only genuinely new axis is worker readiness, because
nothing before P1-S7 needed to know whether a Celery worker could actually pick
the job up.

Two design points:

* **A gate failure is not a test failure.** The gate returning `ready=False`
  puts the run in `BLOCKED_BEFORE_START` with the blockers attached. No item is
  dispatched, and no item is marked FAIL — see `outcomes.py` for why that
  distinction is enforced rather than assumed.

* **The verdict is persisted by value** onto `execution_runs.readiness`. A run
  blocked at 09:00 must still be explainable at 17:00 after the environment
  recovered, which a re-probe at read time could not do.

Per-axis rollup, not just a flat list, because the UI's readiness indicator and
the blocker panel both need to say *which* axis failed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project_application import ProjectApplication
from app.services.automation_runner import readiness as runner_readiness
from app.services.automation_runner import preflight

# The five axes the tracker names. Order is the order the UI lists them in.
AXES = ("environment", "application", "data", "framework", "worker")

# Which runner-level check belongs to which axis. Keeping this mapping explicit
# beats inferring it from the check name, because a renamed probe should be a
# visible edit here rather than a check that silently stops being attributed.
_AXIS_BY_CHECK = {
    "application_url_reachable": "application",
    "credentials_configured": "application",
    "test_data_present": "data",
    "api_dependency_healthy": "environment",
    "db_validation_endpoint_reachable": "environment",
    "browser_deps_installed": "framework",
    "environment_not_under_maintenance": "environment",
}


@dataclass(slots=True)
class GateCheck:
    axis: str
    name: str
    passed: bool
    detail: str
    # False for a probe whose absence is legitimate (an optional dependency that
    # is not configured). Lets the UI distinguish "passed" from "not applicable"
    # without a third boolean state.
    blocking: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "axis": self.axis,
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "blocking": self.blocking,
        }


@dataclass
class GateResult:
    checks: list[GateCheck] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return all(c.passed for c in self.checks if c.blocking)

    @property
    def blockers(self) -> list[GateCheck]:
        return [c for c in self.checks if c.blocking and not c.passed]

    def axis_ready(self, axis: str) -> bool:
        relevant = [c for c in self.checks if c.axis == axis and c.blocking]
        return all(c.passed for c in relevant)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ready": self.ready,
            "axes": {axis: self.axis_ready(axis) for axis in AXES},
            "checks": [c.as_dict() for c in self.checks],
            "blockers": [c.as_dict() for c in self.blockers],
        }


def _worker_check() -> GateCheck:
    """Can a Celery worker actually take this job?

    `control.ping` is a real round trip to the broker, so a dead worker or an
    unreachable Redis both surface here as a blocker instead of as a run that
    sits in QUEUED forever with no explanation.
    """
    try:
        from app.worker.celery_app import celery_app

        replies = celery_app.control.ping(timeout=2.0) or []
    except Exception as exc:  # broker unreachable, misconfigured, etc.
        return GateCheck(
            "worker",
            "worker_available",
            False,
            f"Could not reach the task broker to confirm a worker is available: {exc}",
        )
    if not replies:
        return GateCheck(
            "worker",
            "worker_available",
            False,
            "No Celery worker responded to a ping. Start the worker service — "
            "the run would otherwise sit queued with nothing to execute it.",
        )
    names = sorted(name for reply in replies for name in reply)
    return GateCheck(
        "worker",
        "worker_available",
        True,
        f"{len(names)} worker(s) responded: {', '.join(names)}",
    )


def _framework_checks(frameworks: set[str]) -> list[GateCheck]:
    """One check per distinct framework in the snapshot.

    A mixed suite is only as ready as its least-supported framework, and the
    operator needs to know *which* one is missing. A member whose framework has
    no registered runner is not silently skipped — it becomes a blocker here and
    a BLOCKED item at dispatch (contract Section 2.1.8).
    """
    checks: list[GateCheck] = []
    for framework in sorted(frameworks):
        available, detail = preflight.is_available(framework)
        checks.append(
            GateCheck("framework", f"framework_available:{framework}", available, detail)
        )
    return checks


async def _resolve_application_url(
    db: AsyncSession, *, application_id: int | None, environment: str | None
) -> tuple[str | None, str | None]:
    """Return (url, why_missing). Never raises for missing configuration."""
    if application_id is None:
        return None, "The snapshot member resolved no application."
    application = (
        await db.execute(
            select(ProjectApplication).where(ProjectApplication.id == application_id)
        )
    ).scalar_one_or_none()
    if application is None:
        return None, f"Application {application_id} no longer exists."
    urls = application.environment_urls or {}
    if not environment:
        return None, f"No environment resolved for application '{application.name}'."
    url = urls.get(environment)
    if not url:
        configured = ", ".join(sorted(urls)) or "none"
        return None, (
            f"Application '{application.name}' has no URL for environment "
            f"'{environment}' (configured: {configured})."
        )
    return url, None


async def check_suite_run_readiness(
    db: AsyncSession,
    *,
    application_id: int | None,
    environment: str | None,
    frameworks: set[str],
    test_data_present: bool = True,
    test_data_detail: str | None = None,
    credentials_required: bool = False,
) -> GateResult:
    """Evaluate all five axes for one suite run.

    `frameworks` is the distinct set declared by the snapshot's members, so a
    mixed suite is gated on every framework it actually needs rather than on one
    representative.
    """
    checks: list[GateCheck] = []

    url, why_missing = await _resolve_application_url(
        db, application_id=application_id, environment=environment
    )
    if url is None:
        checks.append(
            GateCheck(
                "application",
                "application_url_configured",
                False,
                why_missing or "No application URL could be resolved.",
            )
        )

    inputs = runner_readiness.ReadinessInputs(
        application_url=url,
        credentials_required=credentials_required,
        test_data_present=test_data_present,
        test_data_detail=(
            test_data_detail
            # P1-S6 Test Data Selection is not built yet, so there is no lease or
            # reservation to verify. Saying so is honest; asserting the data is
            # present would not be.
            or "No test-data reservation exists to verify — P1-S6 Test Data "
            "Selection is not implemented, so this axis is reported as not "
            "applicable rather than as passing."
        ),
        # `framework` on the runner inputs drives its single browser-deps probe;
        # the per-framework checks below supersede it for a mixed suite, so pick
        # any member framework for the legacy field and ignore its verdict.
        framework=next(iter(sorted(frameworks)), "playwright"),
    )
    runner_result = await runner_readiness.check_readiness(inputs)
    for check in runner_result.checks:
        axis = _AXIS_BY_CHECK.get(check.name, "environment")
        # The runner's own browser-deps probe is replaced by the per-framework
        # checks below — keeping both would double-count a mixed suite.
        if check.name == "browser_deps_installed":
            continue
        # Test data is reported, never enforced, until P1-S6 exists.
        blocking = check.name != "test_data_present"
        checks.append(GateCheck(axis, check.name, check.passed, check.detail, blocking))

    checks.extend(_framework_checks(frameworks))
    checks.append(_worker_check())

    return GateResult(checks=checks)
