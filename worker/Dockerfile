FROM python:3.12-slim
WORKDIR /app

COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir -e .

COPY worker ./worker
ENV PYTHONPATH=/app

CMD ["celery", "-A", "worker.celery_app.celery_app", "worker", "--loglevel=info"]
