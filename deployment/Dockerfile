# ── Stage 1: Build Frontend ─────────────────────────────────────────────────
FROM node:20-alpine AS frontend-builder

WORKDIR /build
COPY apps/frontend/package.json apps/frontend/package-lock.json* ./
RUN npm install --frozen-lockfile 2>/dev/null || npm install
COPY apps/frontend/ .
RUN npm run build

# ── Stage 2: Production Image ────────────────────────────────────────────────
FROM python:3.12-slim

LABEL org.opencontainers.image.title="SoundTouch Open Cloud" \
      org.opencontainers.image.description="Local Bose SoundTouch cloud replacement" \
      org.opencontainers.image.source="https://github.com/grimo77/SoundFlow" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STOC_PORT=7777

# System deps for network scanning
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python backend
COPY apps/backend/pyproject.toml ./
COPY apps/backend/src/ ./src/
RUN pip install --no-cache-dir -e "."

# Copy built frontend into static dir served by FastAPI
COPY --from=frontend-builder /build/../../.out/dist/ ./static/

# Serve static files from FastAPI
COPY deployment/serve_static.py ./

# Data directory for SQLite DB and .env
RUN mkdir -p /data
VOLUME ["/data"]

EXPOSE 7777

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
  CMD curl -f http://localhost:7777/health || exit 1

CMD ["python", "-m", "uvicorn", "soundtouch.main:app", \
     "--host", "0.0.0.0", "--port", "7777", "--workers", "1"]
