"""Shared plumbing for containerized runners.

Extracted when the pytest runner arrived: the daemon check, the sandbox flags,
the workspace ownership fix and the container teardown are properties of *running
a test in a container*, not of any one framework. Duplicating them per framework
is how a sandbox control silently ends up applied to one runner and not the
other, which would be worse than having no sandbox at all — the gap would be
invisible.

Framework-specific modules supply only their own image command and their own
result parsing.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def docker_available() -> tuple[bool, str]:
    """Real check: CLI present AND the daemon reachable through the socket."""
    if shutil.which("docker") is None:
        return False, (
            "docker CLI not found in this image — rebuild it (the Dockerfile "
            "installs docker-ce-cli) or set AUTOMATION_RUNNER_MODE=local."
        )
    try:
        proc = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, f"docker daemon not reachable: {exc}"
    if proc.returncode != 0:
        return False, (
            "docker daemon not reachable — is /var/run/docker.sock mounted into this "
            f"container? ({proc.stderr.strip() or 'no error output'})"
        )
    return True, f"docker server {proc.stdout.strip()}"


def sandbox_args() -> list[str]:
    """Confinement flags for a spawned runner container (AUT-002).

    The container executes generated or user-edited test code, which is
    untrusted by definition. Before this it ran as root with every capability,
    a writable root filesystem, no resource ceiling and no privilege-escalation
    guard — so a script that broke out of its test framework had the same
    authority as the runner image itself.

    Each flag is separately configurable rather than hidden behind one
    "sandbox on/off" switch: loosening a specific control should be a visible,
    individually justified decision, not a single toggle that silently removes
    all of them.
    """
    args: list[str] = []

    if settings.automation_docker_run_as_root:
        # Retained as an escape hatch for images built before
        # PLAYWRIGHT_BROWSERS_PATH moved out of /root, where a non-root process
        # cannot reach Chromium at all.
        args += ["--user", "root"]
    else:
        args += ["--user", settings.automation_docker_run_as_user]

    if settings.automation_docker_drop_capabilities:
        # A browser or pytest run needs no Linux capabilities whatsoever.
        args += ["--cap-drop", "ALL"]

    if settings.automation_docker_no_new_privileges:
        # Blocks setuid binaries inside the image from regaining privilege.
        args += ["--security-opt", "no-new-privileges"]

    if settings.automation_docker_seccomp_profile:
        args += ["--security-opt", f"seccomp={settings.automation_docker_seccomp_profile}"]
    if settings.automation_docker_apparmor_profile:
        args += ["--security-opt", f"apparmor={settings.automation_docker_apparmor_profile}"]

    if settings.automation_docker_read_only_rootfs:
        # Chromium, npx and pip all need scratch space, and with a read-only
        # root they must get it somewhere that does not persist: a tmpfs is
        # discarded with the container, so nothing a script writes outlives its
        # own run.
        args += [
            "--read-only",
            "--tmpfs",
            f"/tmp:rw,noexec,nosuid,size={settings.automation_docker_tmpfs_size_mb}m",
        ]

    if settings.automation_docker_memory_limit:
        args += ["--memory", settings.automation_docker_memory_limit]
    if settings.automation_docker_cpu_limit:
        args += ["--cpus", settings.automation_docker_cpu_limit]
    if settings.automation_docker_pids_limit:
        # A fork bomb in generated code should exhaust its own container, not
        # the host's process table.
        args += ["--pids-limit", str(settings.automation_docker_pids_limit)]

    return args


def runner_uid_gid() -> tuple[int, int] | None:
    """The uid:gid the container will run as, or None when it runs as root."""
    if settings.automation_docker_run_as_root:
        return None
    raw = (settings.automation_docker_run_as_user or "").strip()
    try:
        uid_str, _, gid_str = raw.partition(":")
        return int(uid_str), int(gid_str or uid_str)
    except ValueError:
        return None


def prepare_workspace_ownership(workspace_dir: Path) -> str | None:
    """Make the workspace writable by the unprivileged runner uid.

    Workspaces are created by a privileged process, and both frameworks write
    back into them — Playwright its `test-results/`, pytest its JSON report. A
    non-root container therefore fails with EACCES partway through, after the
    test has already started, so the failure surfaces as a confusing "no results"
    rather than as a permissions problem.

    Returns None on success, or a message explaining why the run cannot proceed.
    """
    target = runner_uid_gid()
    if target is None:
        return None
    if not hasattr(os, "chown"):  # non-POSIX host; only reachable in tests
        return None

    uid, gid = target
    try:
        for path in [workspace_dir, *workspace_dir.rglob("*")]:
            # Symlinks (workspace/node_modules → the npm global root) must not
            # be followed: chowning through one would rewrite the image's own
            # module tree.
            if path.is_symlink():
                continue
            os.chown(path, uid, gid)
    except (OSError, PermissionError) as exc:
        return (
            f"The runner container is configured to execute as {uid}:{gid}, but the "
            f"workspace could not be given to that user ({exc}). Either run the "
            "executor with enough privilege to chown its workspaces, or set "
            "AUTOMATION_DOCKER_RUN_AS_ROOT=true to accept an unconfined runner."
        )
    return None


def build_run_command(
    *,
    container_name: str,
    workspace_dir: Path,
    environment: str | None,
    image_command: list[str],
    extra_env: dict[str, str] | None = None,
) -> list[str]:
    """Assemble the full `docker run` argv.

    The image, the mount and the sandbox come from configuration; the caller
    supplies only what to execute inside. Nothing here takes a free-form flag,
    so a caller cannot widen the container's authority.
    """
    cmd = [
        "docker", "run", "--rm",
        "--name", container_name,
        *sandbox_args(),
        "-v", f"{settings.automation_docker_volume}:{settings.automation_docker_storage_mount}",
        "-w", workspace_dir.resolve().as_posix(),
        "-e", f"AUTOMATION_ENV={environment or ''}",
        "-e", "CI=1",
    ]
    for key, value in (extra_env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    if settings.automation_docker_network:
        cmd += ["--network", settings.automation_docker_network]
    cmd += [settings.automation_docker_image, *image_command]
    return cmd


async def kill_container(container_name: str) -> None:
    """Stop a spawned container by name.

    Killing the `docker run` client alone would leave the container executing,
    which is exactly the case cancellation and timeouts have to handle.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "kill", container_name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=15)
    except (OSError, asyncio.TimeoutError):
        # Best effort: the container may already be gone, and failing to kill
        # something that no longer exists must not mask the real outcome.
        pass
