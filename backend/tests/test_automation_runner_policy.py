"""Wave 1 P0-01 / partial AUT-001: runner mode policy and env allowlist.

Two defects are covered here.

The first is that `run_script_for_execution` used to hand `runner_mode=None`
straight to `get_runner_for_framework`, which falls through to the local
subprocess map. Every governed caller — asset dry run, suite command center —
omitted the argument, so the paths with the most governance ran with the least
isolation. Policy is now server-owned and refuses rather than downgrades.

The second is that both local runners built the child environment as
`{**os.environ, ...}`, handing every worker secret to generated test code.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.config import Settings
from app.services.automation_runner import dispatcher
from app.services.automation_runner.env_policy import build_runner_env
from app.services.automation_runner.policy import resolve_runner_mode


def _settings(**overrides) -> Settings:
    # Production requires a non-default secret key of at least 32 chars, so
    # supply one unconditionally rather than per-test.
    overrides.setdefault("app_secret_key", "test-secret-key-with-sufficient-length-1234")
    return Settings(**overrides)


# ── Runner mode policy ──────────────────────────────────────────────────────


def test_local_mode_is_permitted_in_local_app_env():
    decision = resolve_runner_mode(None, settings=_settings(app_env="local"))
    assert decision.permitted
    assert decision.mode == "local"


@pytest.mark.parametrize("app_env", ["staging", "production"])
def test_local_mode_is_refused_outside_development(app_env):
    """Fail closed: no explicit opt-in means no in-worker execution."""
    decision = resolve_runner_mode(None, settings=_settings(app_env=app_env))
    assert not decision.permitted
    assert decision.mode == "local"
    assert "not permitted" in decision.reason


def test_explicit_opt_in_overrides_the_environment_default():
    decision = resolve_runner_mode(
        None,
        settings=_settings(app_env="production", automation_allow_local_runner=True),
    )
    assert decision.permitted


def test_requested_local_is_refused_even_when_the_server_default_is_docker():
    """A caller preference cannot widen policy — that was the whole bug."""
    decision = resolve_runner_mode(
        "local",
        settings=_settings(app_env="production", automation_runner_mode="docker"),
    )
    assert not decision.permitted


def test_docker_mode_is_permitted_regardless_of_app_env():
    decision = resolve_runner_mode(
        "docker", settings=_settings(app_env="production")
    )
    assert decision.permitted and decision.mode == "docker"


def test_unknown_mode_is_refused_rather_than_defaulted():
    decision = resolve_runner_mode("kubernetes", settings=_settings())
    assert not decision.permitted
    assert "Unknown runner mode" in decision.reason


@pytest.mark.asyncio
async def test_dispatcher_refuses_instead_of_running_when_policy_blocks(monkeypatch, tmp_path):
    """A refusal must reach the caller as a failed run with a reason, not as a
    silent downgrade and not as an exception."""
    monkeypatch.setattr(
        dispatcher,
        "resolve_runner_mode",
        lambda requested=None: __import__(
            "app.services.automation_runner.policy", fromlist=["resolve_runner_mode"]
        ).resolve_runner_mode(requested, settings=_settings(app_env="production")),
    )

    result = await dispatcher.run_script_for_execution(
        framework="playwright",
        workspace=Path(tmp_path),
        script_file_name="x.spec.ts",
        execution_command=None,
        environment="SIT",
    )

    assert result.run_status == "failed"
    assert result.results == []
    assert "not permitted" in result.error_message
    assert result.metadata["runner_policy"] == "refused"


@pytest.mark.asyncio
async def test_dispatcher_records_the_effective_mode_in_metadata(monkeypatch, tmp_path):
    """Evidence has to show the isolation level a result was produced under."""
    seen = {}

    class _FakeRunner:
        name = "fake"

        async def run(self, **kwargs):
            from app.services.automation_runner.base import RunnerResult

            seen.update(kwargs)
            return RunnerResult(
                run_status="completed",
                results=[],
                duration_seconds=0.0,
                log_path=None,
                metadata={"runner": self.name},
            )

    monkeypatch.setattr(
        dispatcher, "get_runner_for_framework", lambda framework, mode: _FakeRunner()
    )

    result = await dispatcher.run_script_for_execution(
        framework="playwright",
        workspace=Path(tmp_path),
        script_file_name="x.spec.ts",
        execution_command=None,
        environment="SIT",
    )

    assert result.metadata["runner_mode"] == "local"
    assert result.metadata["runner_policy_permitted"] is True
    # The runner's own metadata is preserved, not clobbered by the policy keys.
    assert result.metadata["runner"] == "fake"


def test_unregistered_framework_still_reports_the_policy_decision(tmp_path):
    import asyncio

    result = asyncio.run(
        dispatcher.run_script_for_execution(
            framework="katalon",
            workspace=Path(tmp_path),
            script_file_name="x",
            execution_command=None,
            environment="SIT",
        )
    )
    assert result.run_status == "failed"
    assert "No runner registered" in result.error_message
    assert "runner_mode" in result.metadata


# ── Environment allowlist ───────────────────────────────────────────────────


_SECRETS = {
    "DATABASE_URL": "postgresql://user:password@db:5432/stlc",
    "APP_SECRET_KEY": "signing-key",
    "OPENAI_API_KEY": "sk-live",
}
_ESSENTIALS = {"PATH": "/usr/bin", "HOME": "/root"}
_TEST_FACING = {"BASE_URL": "https://sit.example.com"}


def test_enforcement_is_the_default():
    """The audit ran, showed 68 of 73 variables withheld with nothing a test
    legitimately reads among them, and the switch was thrown. A deployment that
    regresses this default silently hands every provider key back to generated
    test code."""
    env, withheld = build_runner_env(
        source={**_ESSENTIALS, **_TEST_FACING, **_SECRETS}, settings=_settings()
    )
    assert "DATABASE_URL" not in env
    assert set(withheld) == set(_SECRETS)


def test_audit_mode_passes_everything_through_but_reports_what_would_be_withheld():
    """Still available for a deployment whose scripts read something unusual."""
    env, withheld = build_runner_env(
        source={**_ESSENTIALS, **_TEST_FACING, **_SECRETS},
        settings=_settings(automation_runner_env_allowlist_enforced=False),
    )
    assert env["DATABASE_URL"] == _SECRETS["DATABASE_URL"]
    # The audit list is accurate, which is what made enforcement safe to enable.
    assert withheld == ["APP_SECRET_KEY", "DATABASE_URL", "OPENAI_API_KEY"]


def test_enforced_mode_withholds_secrets_and_keeps_runtime_essentials():
    env, withheld = build_runner_env(
        source={**_ESSENTIALS, **_TEST_FACING, **_SECRETS},
        settings=_settings(automation_runner_env_allowlist_enforced=True),
    )
    assert "DATABASE_URL" not in env
    assert "APP_SECRET_KEY" not in env
    assert "OPENAI_API_KEY" not in env
    # Stripping PATH/HOME would break the runner rather than harden it.
    assert env["PATH"] == "/usr/bin"
    assert env["HOME"] == "/root"
    assert env["BASE_URL"] == _TEST_FACING["BASE_URL"]
    assert set(withheld) == set(_SECRETS)


def test_prefix_entries_match_families_of_variables():
    env, _ = build_runner_env(
        source={"PLAYWRIGHT_BROWSERS_PATH": "/ms", "PLAYWRIGHTX": "no"},
        settings=_settings(
            automation_runner_env_allowlist_enforced=True,
            automation_runner_env_allowlist="PLAYWRIGHT_*",
        ),
    )
    assert "PLAYWRIGHT_BROWSERS_PATH" in env
    assert "PLAYWRIGHTX" not in env


def test_overrides_survive_enforcement():
    """AUTOMATION_ENV and friends are set by the runner, not inherited, so they
    must land in the child env even when the allowlist is at its strictest."""
    env, _ = build_runner_env(
        source=_SECRETS,
        overrides={"AUTOMATION_ENV": "SIT", "CI": "1"},
        settings=_settings(
            automation_runner_env_allowlist_enforced=True,
            automation_runner_env_allowlist="",
        ),
    )
    assert env["AUTOMATION_ENV"] == "SIT"
    assert env["CI"] == "1"
