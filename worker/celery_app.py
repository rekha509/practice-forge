"""Celery app. Real tasks (P10) live in `worker/tasks.py` — `include`
below is what makes `celery -A worker.celery_app.celery_app worker`
actually register them, since that invocation only imports this module,
not `worker.tasks` directly."""

from __future__ import annotations

from celery import Celery

from practice_forge.config import get_settings

settings = get_settings()

celery_app = Celery(
    "practice_forge",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["worker.tasks"],
)
