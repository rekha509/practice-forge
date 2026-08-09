"""P1 gate: `docker compose up -d && pytest tests/test_sandbox.py -v` must
pass, proving the sandbox blocks network and enforces CPU and memory caps.

Requires a running Docker daemon reachable from the host. The base sandbox
image is built once per session if missing.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from docker.errors import ImageNotFound

import docker
from practice_forge.sandbox.runner import DEFAULT_IMAGE, run_code

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def _sandbox_base_image() -> None:
    client = docker.from_env()
    try:
        client.images.get(DEFAULT_IMAGE)
    except ImageNotFound:
        client.images.build(
            path=str(REPO_ROOT / "docker" / "sandbox"),
            dockerfile="base.Dockerfile",
            tag=DEFAULT_IMAGE,
        )


def test_normal_program_runs_cleanly() -> None:
    result = run_code("print('hello from sandbox')\n", timeout_s=10)
    assert result.ok is True
    assert "hello from sandbox" in result.stdout


def test_network_is_blocked() -> None:
    code = (
        "import socket\n"
        "s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\n"
        "s.settimeout(3)\n"
        "try:\n"
        "    s.connect(('8.8.8.8', 53))\n"
        "    print('CONNECTED')\n"
        "except OSError as e:\n"
        "    print(f'BLOCKED: {e}')\n"
    )
    result = run_code(code, timeout_s=10)
    assert "BLOCKED" in result.stdout
    assert "CONNECTED" not in result.stdout


def test_cpu_wall_clock_cap_kills_infinite_loop() -> None:
    result = run_code("while True:\n    pass\n", timeout_s=3)
    assert result.timed_out is True
    assert result.ok is False


def test_memory_cap_oom_kills_runaway_allocation() -> None:
    code = (
        "chunks = []\n"
        "while True:\n"
        "    chunks.append(bytearray(50 * 1024 * 1024))  # 50MB per iteration\n"
    )
    result = run_code(code, timeout_s=15, mem_limit_mb=128)
    assert result.oom_killed is True
    assert result.ok is False


def test_readonly_fs_blocks_writes_outside_tmp_but_allows_tmp() -> None:
    code = (
        "outside_ok = False\n"
        "try:\n"
        "    with open('/etc/should_not_write', 'w') as f:\n"
        "        f.write('x')\n"
        "    outside_ok = True\n"
        "except OSError:\n"
        "    pass\n"
        "with open('/tmp/scratch.txt', 'w') as f:\n"
        "    f.write('ok')\n"
        "print('OUTSIDE_WRITE_OK' if outside_ok else 'OUTSIDE_BLOCKED')\n"
        "print('TMP_WRITE_OK')\n"
    )
    result = run_code(code, timeout_s=10)
    assert "OUTSIDE_BLOCKED" in result.stdout
    assert "TMP_WRITE_OK" in result.stdout
    assert result.ok is True
