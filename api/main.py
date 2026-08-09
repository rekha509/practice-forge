"""Minimal FastAPI stub. Real routes (upload, job progress SSE, problem set
download) land in P10 — this only exists so P1's docker-compose stack has a
working api container to prove the topology out."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="practice-forge api")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
