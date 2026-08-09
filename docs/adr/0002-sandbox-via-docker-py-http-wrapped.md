# 2. Sandbox execution via docker-py, isolated behind an HTTP wrapper service

## Status
Accepted

## Context
Every generated Part A / Part B program must run with no network, capped
CPU/memory, and a read-only root filesystem (spec: "no network, 30s CPU cap,
2GB memory, read-only FS except /tmp"). Something in the stack needs access
to the Docker daemon to spawn these throwaway containers.

Giving the Celery `worker` container direct access to `/var/run/docker.sock`
was the simplest option, but it means a compromised worker (e.g. via a
`pip`-installed dependency, or a bug in our own task code) has root-equivalent
access to the *host*, not just to the sandbox it's supposed to be
constraining — the containers it spawns are a much smaller concern than the
socket access itself.

## Decision
- Docker sandbox execution lives in `src/practice_forge/sandbox/runner.py`,
  built on the `docker` SDK (docker-py).
- It is exposed only through a dedicated `sandbox-runner` FastAPI service
  (`sandbox_runner/`), which is the *only* container in docker-compose.yml
  with the Docker socket mounted.
- The `worker` service talks to `sandbox-runner` over the internal compose
  network via plain HTTP, never touching the socket itself.
- CPU-seconds are enforced as a wall-clock timeout against a 1-CPU quota
  (`nano_cpus=1_000_000_000`), not tracked cgroup CPU-time accounting. For
  the single-threaded numeric scripts this system generates, wall-clock
  time at 1 CPU *is* CPU-seconds; the added complexity of precise cgroup
  CPU-time polling wasn't justified for that workload.
- Read-only rootfs + a `tmpfs` mount at `/tmp` (see `base.Dockerfile`,
  `runner.py`) is enforced per-container, not just documented as a
  convention.

## Consequences
- Blast radius of a compromised worker task is now limited to whatever the
  Celery/API containers themselves can reach — not the host Docker daemon.
- Adds one extra network hop (worker -> sandbox-runner) and one more service
  to run locally, in exchange for that isolation.
- If a future stage needs more precise CPU-time accounting (rather than
  wall-clock-at-1-CPU), it will mean adding cgroup stat polling into
  `runner.py` — deferred until real numeric workloads show it's actually
  needed.
