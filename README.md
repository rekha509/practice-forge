# practice-forge

Ingests a core-engineering textbook PDF (Mechanical, Civil, Electrical,
Electronics, Chemical, or Computer Science) and produces an original,
execution-verified 20-problem practice set per course run: student handout,
faculty solutions manual, and a runnable `code/` folder — never repeating a
concept already issued for that course, even across different books or
re-runs of the same book. See the project brief in PROGRESS.md's history for
the full spec; this README covers day-to-day setup.

## Setup

1. **Python 3.12** and **Docker Desktop** (with the Docker daemon running).
2. Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY`. Never
   commit `.env` — it's gitignored.
3. Install the package in editable mode for local (non-container) work —
   CLI, tests, Alembic:
   ```
   pip install -e ".[dev]"
   ```

## Running the stack

```
docker compose up -d
```

Brings up: `db` (Postgres + pgvector), `redis`, `sandbox-base` (builds the
shared sandbox image and exits — nothing runs in it), `sandbox-runner` (the
only container with the Docker socket mounted — see
[docs/adr/0002](docs/adr/0002-sandbox-via-docker-py-http-wrapped.md)), `api`,
and `worker`.

## Database migrations

```
alembic upgrade head
```

Reads `DATABASE_URL` from `.env` (host-oriented — `localhost`, since Alembic
runs from the host, not inside a container).

## Tests

```
pytest tests/ -v
```

`tests/test_sandbox.py` is Phase P1's gate — it requires a running Docker
daemon and builds `practice-forge-sandbox-base:latest` on first run. Tests
marked `@pytest.mark.llm` make real Anthropic API calls; they're deselected
by default:

```
pytest -m "not llm"
```

## CLI

```
pf profiles list          # discipline profiles — fully working now
pf ingest <path-to-pdf>   # Phase P2 — not yet implemented
pf generate --book <id>   # Phases P6-P10 — not yet implemented
```

## Project layout

```
src/practice_forge/    platform code (type-checked, linted; see pyproject.toml)
  models/               Pydantic domain models
  db/                   SQLAlchemy ORM + session management
  profiles/             discipline profile loader (see profiles/*.yaml)
  sandbox/              Docker sandbox runner
  cli/                  `pf` command
api/                    FastAPI app (thin — real routes land in P10)
worker/                 Celery app (thin — real tasks land starting P2)
sandbox_runner/         HTTP wrapper around sandbox/runner.py; the only
                        service with docker.sock mounted
profiles/               discipline profile YAMLs (declarative, not code)
prompts/                versioned LLM prompt files (never inline strings)
migrations/             Alembic
tests/                  pytest; @pytest.mark.llm gates real API-call tests
docs/adr/               architecture decision records
```

Generated student-facing code (in each problem set's `code/` folder) follows
a *different*, deliberately simple standard than platform code — see the
CODE DESIGN section referenced in PROGRESS.md. It is not type-checked or
linted by this repo's mypy/ruff config.

## Status

This is being built phase-by-phase; see `PROGRESS.md` at the repo root for
exactly what's done, what's next, and what's blocked.
