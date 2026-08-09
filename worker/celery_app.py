"""Celery app skeleton. Real tasks (S1-S10 pipeline stages) land starting P2 —
this only proves the worker connects to Redis and idles cleanly for P1."""

from __future__ import annotations

from celery import Celery

from practice_forge.config import get_settings

settings = get_settings()

celery_app = Celery(
    "practice_forge",
    broker=settings.redis_url,
    backend=settings.redis_url,
)
