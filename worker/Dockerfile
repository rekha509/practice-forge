FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY worker ./worker
# Every LLM-touching stage this worker runs (S1's fallback, S8, S9) reads
# config/llm_routing.yaml and its own prompts/*.md at call time via paths
# resolved from REPO_ROOT -- without these the image builds and the
# container stays up (celery itself needs neither file), but the first
# real ingest/generate job crashes with FileNotFoundError the moment it
# tries to make an LLM call. Found live: a real upload's ingest job sat at
# "queued" then failed here once the OTHER stale-image bug was fixed.
COPY config ./config
COPY prompts ./prompts
# Same real gap as config/prompts above, found live the same way: S7
# selection/S8 variant generation load the book's DisciplineProfile
# (profiles/<key>.yaml) at call time -- without this, generate crashes
# with FileNotFoundError on the very first real attempt after any book's
# ingest completes.
COPY profiles ./profiles
ENV PYTHONPATH=/app

CMD ["celery", "-A", "worker.celery_app.celery_app", "worker", "--loglevel=info"]
