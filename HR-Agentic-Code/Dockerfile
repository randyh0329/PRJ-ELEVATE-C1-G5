# syntax=docker/dockerfile:1
FROM python:3.13-slim AS base

# Prevent Python from writing .pyc files and buffer stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PORT=8080

WORKDIR /app

# Install system utilities needed for healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY config/ ./config/
COPY src/ ./src/
COPY data/ ./data/
COPY pyproject.toml .

# Create and switch to non-root application user for least-privilege container security
RUN useradd -m -u 10001 appuser && \
    chown -R appuser:appuser /app
USER appuser

# Document exposed port for Cloud Run
EXPOSE 8080

# Container health probe
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Launch production ASGI server (FastAPI)
CMD ["sh", "-c", "exec uvicorn src.main:app --host 0.0.0.0 --port ${PORT}"]
