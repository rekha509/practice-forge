"""The real P10 FastAPI app — library + resumable ingest + generate/
reshuffle/new-set + downloads, all backed by Celery jobs for anything
that touches marker/S8/S9 (see `worker/tasks.py`). CORS is wide open for
the Next.js dev server (P11); tighten before any real deployment."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import books, jobs, problem_sets

app = FastAPI(title="practice-forge api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(books.router)
app.include_router(jobs.router)
app.include_router(problem_sets.router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
