# Multi-Stage Production Dockerfile for Elevate HR Agentic Solution (MVP 1)
# Stage 1: Build & Dependency Resolution
FROM python:3.13-slim AS builder

WORKDIR /build

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Stage 2: Minimal Distroless / Hardened Runtime
FROM python:3.13-slim AS runner

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/home/appuser/.local/bin:${PATH}" \
    PYTHONPATH="/app"

RUN groupadd -g 10001 appuser && \
    useradd -u 10001 -g appuser -m -s /bin/bash appuser

COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local

COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser fixtures/ ./fixtures/
COPY --chown=appuser:appuser mocks/ ./mocks/
COPY --chown=appuser:appuser prompts/ ./prompts/
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser pyproject.toml .

USER appuser

EXPOSE 8000 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "src.gateway.app:gateway_app", "--host", "0.0.0.0", "--port", "8000"]
