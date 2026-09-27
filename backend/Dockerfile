# syntax=docker/dockerfile:1

FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    WEB_CONCURRENCY=2

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /install /usr/local

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/data/faiss /app/data/workspace \
    && chown -R app:app /app

WORKDIR /app
COPY --chown=app:app . .
RUN chmod +x docker-entrypoint.sh

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8000/health || exit 1

ENTRYPOINT ["./docker-entrypoint.sh"]
# Gunicorn supervises Uvicorn workers (restarts crashed workers, graceful reloads).
# Behind Nginx, trust X-Forwarded-For so rate limiting sees real client IPs.
CMD ["sh", "-c", "exec gunicorn main:app --worker-class uvicorn.workers.UvicornWorker --workers ${WEB_CONCURRENCY} --bind 0.0.0.0:8000 --forwarded-allow-ips='*' --timeout 300 --graceful-timeout 30 --access-logfile -"]
