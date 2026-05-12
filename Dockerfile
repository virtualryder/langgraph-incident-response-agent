# syntax=docker/dockerfile:1.7
#
# Incident Response Agent — production image.
#
# Multi-stage build:
#   • builder  — installs deps into a virtualenv (no build tools in final image)
#   • runtime  — minimal slim image, non-root user, just the venv + app code
#
# Streamlit binds to 0.0.0.0:$PORT (Railway/Render/Fly inject $PORT).
# Local default falls back to 8501.

# ── builder ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Build deps for chromadb's onnxruntime and any native wheels in
# PyGithub / boto3 (cryptography, etc).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install deps first for layer cache efficiency.
COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt

# Pre-warm Chroma's default ONNX embedding model (~80MB) so the runtime
# container doesn't have to download it from HuggingFace on first request.
# Without this, cold-start latency includes the download, and the first
# user request can fail if egress is rate-limited or blocked.
ENV CHROMA_CACHE_DIR=/opt/chroma-cache
RUN mkdir -p /opt/chroma-cache && \
    python -c "import chromadb; c = chromadb.EphemeralClient(); \
        col = c.create_collection('warmup', metadata={'hnsw:space':'cosine'}); \
        col.add(ids=['1'], documents=['warmup doc'])" \
    || echo "Warning: pre-warm failed; runtime will download on first use."


# ── runtime ─────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app \
    # Streamlit server config — redundantly set in .streamlit/config.toml too.
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_ENABLE_CORS=false \
    STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=true \
    # Persistent volume mount points. Railway mounts /data as a volume;
    # the agent writes audit logs and Chroma persistence there so both
    # survive redeploys.
    AUDIT_LOG_DIR=/data/audit \
    CHROMA_PERSIST_DIR=/data/chroma

# Minimal runtime libs only (no compilers shipped).
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system app && useradd --system --gid app --home /app app

# Copy the prepared virtualenv from builder.
COPY --from=builder /opt/venv /opt/venv

# Copy the pre-warmed Chroma embedding model cache.
COPY --from=builder /opt/chroma-cache /opt/chroma-cache
ENV CHROMA_CACHE_DIR=/opt/chroma-cache

WORKDIR /app

# Copy application code (respects .dockerignore).
COPY --chown=app:app . /app

# Pre-create runtime dirs and assign ownership so the non-root user can write.
RUN mkdir -p /data/audit /data/chroma && \
    chown -R app:app /data /app

USER app

# Railway / most PaaS inject $PORT. Streamlit's health endpoint is /_stcore/health.
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS "http://localhost:${PORT:-8501}/_stcore/health" || exit 1

# Shell form so $PORT expands at runtime.
CMD streamlit run app.py \
    --server.address=0.0.0.0 \
    --server.port=${PORT:-8501} \
    --server.headless=true \
    --browser.gatherUsageStats=false
