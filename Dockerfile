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
COPY pyproject.toml .

# The policy corpus. Not optional, and its absence is silent: `okf_store` logs
# an error and carries on with an empty register, so every policy question -
# in every language - comes back "I could not find an approved policy on this
# topic in our handbook". That reads as "the handbook does not cover this" and
# is indistinguishable, from the outside, from a working service answering
# honestly. It is 344 KB.
COPY okf/ ./okf/
COPY "ALTOSTRAT SINGAPORE EMPLOYEE POLICY HANDBOOK & CONDUCT GUIDELINES.md" ./

# Build the FAISS index into the image. `var/` is a git-ignored build artefact,
# so it cannot be COPYed from a checkout - it has to be produced here, and if it
# is not produced at all the service silently degrades to the deterministic OKF
# register, which answers only questions phrased in the corpus's own words.
#
# HF_HOME is set inside the image so the embedding model is baked in rather than
# downloaded on the first request: a cold Cloud Run instance reaching out to
# huggingface.co mid-query is both slow and a runtime dependency on a third
# party that the served page does not need to have.
ENV HF_HOME=/app/.cache/huggingface
RUN python -m src.grounding.policy_rag.cli ingest

# Stamp the commit into the image so the running service can report its own
# version. Declared here, after the COPY steps, so changing it does not
# invalidate the cached dependency layers. The image is self-describing as a
# result: `docker run` it anywhere and /health still knows what it is.
# Nothing above copies `.git`, so this is the only way the container can know.
ARG GIT_COMMIT_SHA=unknown
ENV GIT_COMMIT_SHA=${GIT_COMMIT_SHA}

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
