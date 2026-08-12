"""The real P10 FastAPI app — library + resumable ingest + generate/
reshuffle/new-set + downloads, all backed by Celery jobs for anything
that touches marker/S8/S9 (see `worker/tasks.py`).

Confirmed live, twice: `allow_origins=["*"]` already covers ANY origin —
including both :3000 and :3001 (Next.js falls back to :3001 when :3000
is occupied, which has happened during this project's own dev sessions)
and any other port a dev server might land on. Verified via `curl -H
"Origin: ..."` (real `access-control-allow-origin: *` response header)
and via a real headless-browser fetch from :3000. A browser-visible
"Failed to fetch" with this config in place is therefore almost always
the API process itself being unreachable (crashed, wrong port, wrong
container) rather than a CORS rejection — check that first.

`CORS_ALLOW_ORIGINS` (P13): unset/empty keeps the wide-open dev default
above unchanged (every prior real call site — the dev Next.js server, the
tunnel, `pytest`'s TestClient — keeps working exactly as before). Set to
a comma-separated real origin list (e.g. the production frontend's own
hostname) to tighten this for an actual deployment; wide-open CORS on an
API that accepts a real bearer token is a real credential-theft surface
once faculty tokens are worth stealing, not something to ship open by
default just because dev needed it open."""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import books, jobs, problem_sets

app = FastAPI(title="practice-forge api")

_cors_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
_cors_allow_origins = (
    [origin.strip() for origin in _cors_origins_env.split(",") if origin.strip()]
    if _cors_origins_env
    else ["*"]
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router)
app.include_router(jobs.router)
app.include_router(problem_sets.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
