# ── Stage 1: Build Frontend ─────────────────────────────────────────────────
# Pinned to the native build platform ($BUILDPLATFORM) so npm never runs under
# slow QEMU emulation. The frontend output is static, so it works on any arch.
FROM --platform=$BUILDPLATFORM node:20-alpine AS frontend-builder

WORKDIR /app/frontend
COPY apps/frontend/package.json apps/frontend/package-lock.json* ./
RUN npm config set fetch-timeout 300000 && \
    (npm ci 2>/dev/null || npm install)
COPY apps/frontend/ .
RUN npm run build

# ── Stage 2: Production Image ────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="SoundFlow" \
      org.opencontainers.image.description="Local Bose SoundTouch cloud replacement" \
      org.opencontainers.image.source="https://github.com/grimo77/SoundFlow" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STOC_PORT=7777 \
    STATIC_DIR=/app/static \
    PYTHONPATH=/app/src

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies directly (no editable install needed in production)
COPY apps/backend/pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir \
        "fastapi>=0.111" \
        "uvicorn[standard]>=0.29" \
        "httpx>=0.27" \
        "aiosqlite>=0.20" \
        "pydantic>=2.7" \
        "pydantic-settings>=2.3" \
        "websockets>=12"

# Copy backend source
COPY apps/backend/src/ ./src/

# Copy built frontend
COPY --from=frontend-builder /app/frontend/dist/ ./static/

# Data directory for SQLite DB and .env
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE ${STOC_PORT:-7777}

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:${STOC_PORT:-7777}/health || exit 1

CMD ["sh", "-c", "uvicorn soundtouch.main:app --host 0.0.0.0 --port ${STOC_PORT:-7777} --workers 1"]
