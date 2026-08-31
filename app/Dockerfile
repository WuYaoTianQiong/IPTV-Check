FROM node:20-slim AS frontend-builder
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --production=false
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

COPY backend/ ./

COPY --from=frontend-builder /build/dist /app/iptv_check/static

RUN mkdir -p /app/iptv_check/data /app/iptv_check/data/cache_store /app/iptv_check/data/exports /app/iptv_check/data/uploads /app/iptv_check/static

EXPOSE 9528

ENV PYTHONUNBUFFERED=1
ENV IPTV_CHECK_HOST=0.0.0.0
ENV IPTV_CHECK_PORT=9528

VOLUME ["/app/iptv_check/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:9528/healthz || exit 1

CMD ["python", "-m", "iptv_check.server.main"]
