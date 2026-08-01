"""Wave 4 / AUT-002: confinement flags on the spawned runner container.

The Docker runner used to spawn `docker run --rm --user root` with no capability
drop, no privilege-escalation guard, a writable root filesystem and no resource
ceiling. A generated test that escaped Playwright had the same authority inside
its container as the runner image itself, and nothing bounded what it consumed.

These assert the argument vector, which is the whole of the control: every flag
here is the only thing standing between untrusted generated code and the
container it runs in.
"""
from __future__ import annotations

import pytest

import app.services.automation_runner.docker_playwright as docker_mod
from app.config import Settings


def _apply(monkeypatch, **overrides) -> list[str]:
    overrides.setdefault("app_secret_key", "test-secret-key-with-sufficient-length-1234")
    monkeypatch.setattr(docker_mod, "settings", Settings(**overrides))
    return docker_mod._sandbox_args()


def test_runner_does_not_run_as_root_by_default(monkeypatch):
    args = _apply(monkeypatch)
    assert "--user" in args
    assert args[args.index("--user") + 1] == "10001:10001"
    assert "root" not in args


def test_root_remains_available_for_images_built_before_the_browser_move(monkeypatch):
    """An older image keeps Chromium under /root/.cache, where a non-root
    process cannot reach it — the escape hatch has to stay reachable."""
    args = _apply(monkeypatch, automation_docker_run_as_root=True)
    assert args[args.index("--user") + 1] == "root"


def test_all_capabilities_are_dropped_by_default(monkeypatch):
    args = _apply(monkeypatch)
    assert "--cap-drop" in args
    assert args[args.index("--cap-drop") + 1] == "ALL"


def test_privilege_escalation_is_blocked_by_default(monkeypatch):
    args = _apply(monkeypatch)
    assert "no-new-privileges" in args


def test_root_filesystem_is_read_only_with_a_scratch_tmpfs(monkeypatch):
    """Chromium and npx need scratch space. A tmpfs gives them somewhere that
    is discarded with the container, so nothing a script writes outlives it."""
    args = _apply(monkeypatch)
    assert "--read-only" in args
    tmpfs = args[args.index("--tmpfs") + 1]
    assert tmpfs.startswith("/tmp:rw")
    assert "noexec" in tmpfs and "nosuid" in tmpfs


def test_resource_ceilings_are_applied(monkeypatch):
    args = _apply(monkeypatch)
    assert args[args.index("--memory") + 1] == "2g"
    assert args[args.index("--cpus") + 1] == "2.0"
    # A fork bomb should exhaust its own container, not the host process table.
    assert args[args.index("--pids-limit") + 1] == "512"


def test_security_profiles_are_passed_through_when_configured(monkeypatch):
    args = _apply(
        monkeypatch,
        automation_docker_seccomp_profile="/profiles/runner.json",
        automation_docker_apparmor_profile="runner-profile",
    )
    assert "seccomp=/profiles/runner.json" in args
    assert "apparmor=runner-profile" in args


def test_profiles_are_omitted_rather_than_passed_empty(monkeypatch):
    """`--security-opt seccomp=` is not the same as leaving docker's default in
    place; an empty value would disable confinement rather than keep it."""
    args = _apply(monkeypatch)
    assert not any(a.startswith("seccomp=") for a in args)
    assert not any(a.startswith("apparmor=") for a in args)


@pytest.mark.parametrize(
    "setting, absent_flag",
    [
        ("automation_docker_drop_capabilities", "--cap-drop"),
        ("automation_docker_no_new_privileges", "--security-opt"),
        ("automation_docker_read_only_rootfs", "--read-only"),
    ],
)
def test_each_control_is_loosened_individually(monkeypatch, setting, absent_flag):
    """There is deliberately no single "disable sandbox" switch: weakening one
    control must be a separate, visible decision."""
    args = _apply(monkeypatch, **{setting: False})
    assert absent_flag not in args
    # The others stay on.
    assert "--user" in args
    assert "--pids-limit" in args


def test_the_full_run_command_carries_the_sandbox(monkeypatch, tmp_path):
    """Guards the wiring, not just the helper: the flags have to reach the
    actual `docker run` argv."""
    workspace = tmp_path / "automation_workspace" / "1-1"
    workspace.mkdir(parents=True)

    monkeypatch.setattr(docker_mod, "docker_available", lambda: (True, "ok"))
    monkeypatch.setattr(
        docker_mod.settings, "automation_docker_storage_mount", str(tmp_path)
    )

    captured = {}

    class _Proc:
        returncode = 0

        class stdout:
            @staticmethod
            async def read(_n):
                return b""

        async def wait(self):
            return 0

        def kill(self):
            pass

    async def fake_exec(*cmd, **_kwargs):
        captured["cmd"] = list(cmd)
        return _Proc()

    monkeypatch.setattr(docker_mod.asyncio, "create_subprocess_exec", fake_exec)

    import asyncio

    asyncio.run(
        docker_mod.DockerPlaywrightRunner().run(
            workspace_dir=workspace,
            script_file_name="specs/x.spec.ts",
            execution_command=None,
            environment="SIT",
            timeout_seconds=30,
        )
    )

    cmd = captured["cmd"]
    assert "--cap-drop" in cmd and "--read-only" in cmd
    assert "no-new-privileges" in cmd
    assert cmd[cmd.index("--user") + 1] == "10001:10001"
