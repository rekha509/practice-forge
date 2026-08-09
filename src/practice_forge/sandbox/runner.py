"""The only place generated (Part A / Part B) code ever executes.

Nothing here trusts the code it runs: no network, one CPU, capped memory,
read-only root filesystem with a small writable /tmp tmpfs for output figures.
CPU-seconds are enforced as wall-clock timeout against a 1-CPU quota, which is
equivalent for the single-threaded numeric scripts this system generates.
"""

from __future__ import annotations

from dataclasses import dataclass

import docker
from docker.errors import NotFound

DEFAULT_IMAGE = "practice-forge-sandbox-base:latest"


@dataclass(frozen=True)
class SandboxResult:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    oom_killed: bool

    @property
    def ok(self) -> bool:
        """True only for a clean exit with no timeout and no OOM kill.
        Always check this, never exit_code alone — a killed process can
        still report exit_code 0 in edge cases."""
        return self.exit_code == 0 and not self.timed_out and not self.oom_killed


def run_code(
    code: str,
    *,
    image: str = DEFAULT_IMAGE,
    timeout_s: int = 15,
    mem_limit_mb: int = 2048,
    network_disabled: bool = True,
) -> SandboxResult:
    """Run `code` as a standalone Python program inside a locked-down container."""
    client = docker.from_env()
    container = client.containers.run(
        image=image,
        command=["python", "-c", code],
        network_disabled=network_disabled,
        mem_limit=f"{mem_limit_mb}m",
        memswap_limit=f"{mem_limit_mb}m",  # no swap headroom: OOM, not thrashing
        nano_cpus=1_000_000_000,  # 1 CPU
        pids_limit=64,
        read_only=True,
        tmpfs={"/tmp": "rw,size=64m"},
        user="65534:65534",  # nobody:nogroup
        security_opt=["no-new-privileges"],
        cap_drop=["ALL"],
        working_dir="/tmp",
        detach=True,
    )
    try:
        timed_out = False
        try:
            wait_result = container.wait(timeout=timeout_s)
            exit_code = wait_result.get("StatusCode")
        except Exception:
            timed_out = True
            container.kill()
            wait_result = container.wait(timeout=5)
            exit_code = wait_result.get("StatusCode")

        stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
        stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")

        state = client.api.inspect_container(container.id)["State"]
        oom_killed = bool(state.get("OOMKilled"))

        return SandboxResult(
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            timed_out=timed_out,
            oom_killed=oom_killed,
        )
    finally:
        try:
            container.remove(force=True)
        except NotFound:
            pass
