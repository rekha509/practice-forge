# The one container allowed to touch the host Docker daemon (see
# docker-compose.yml's docker.sock mount on this service, and no other).
FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY sandbox_runner ./sandbox_runner
ENV PYTHONPATH=/app

CMD ["uvicorn", "sandbox_runner.main:app", "--host", "0.0.0.0", "--port", "9000"]
