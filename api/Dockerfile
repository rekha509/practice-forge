FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY api ./api
# api/routers/{books,problem_sets}.py both import from worker.tasks (to
# .delay() real Celery jobs) - without this the image builds fine but the
# container crashes on startup with ModuleNotFoundError the moment a
# request imports the routers, which uvicorn does at process start. Found
# live: docker compose up looked fine, but the container was actually
# exited, and the browser just saw "Failed to fetch".
COPY worker ./worker
# The chat route (api/routers/problem_sets.py) makes a real LLM call
# in-process, which reads config/llm_routing.yaml and
# prompts/chat_explain_step.md at call time -- same real gap as worker's
# own Dockerfile (see its comment), just not yet hit here since chat was
# only exercised via mocked tests before now.
COPY config ./config
COPY prompts ./prompts
# Not currently read by api/ code directly, but worker/tasks.py (imported
# above for .delay()) does read it -- copied defensively for the same
# reason config/prompts are, after finding that exact gap live in
# worker/Dockerfile.
COPY profiles ./profiles
ENV PYTHONPATH=/app

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
