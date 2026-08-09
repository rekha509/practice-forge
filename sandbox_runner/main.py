"""Thin HTTP wrapper around practice_forge.sandbox.runner.run_code.

Isolates docker.sock access to exactly this one container — the worker calls
this service over the internal compose network and never touches the host
Docker daemon directly.
"""

from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from practice_forge.sandbox.runner import DEFAULT_IMAGE, run_code

app = FastAPI(title="practice-forge sandbox-runner")


class RunRequest(BaseModel):
    code: str
    image: str = DEFAULT_IMAGE
    timeout_s: int = 15
    mem_limit_mb: int = 2048
    network_disabled: bool = True


class RunResponse(BaseModel):
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    oom_killed: bool
    ok: bool


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/run", response_model=RunResponse)
def run(req: RunRequest) -> RunResponse:
    result = run_code(
        req.code,
        image=req.image,
        timeout_s=req.timeout_s,
        mem_limit_mb=req.mem_limit_mb,
        network_disabled=req.network_disabled,
    )
    return RunResponse(
        exit_code=result.exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        timed_out=result.timed_out,
        oom_killed=result.oom_killed,
        ok=result.ok,
    )
