FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[dev]" 2>/dev/null || pip install --no-cache-dir -e .

COPY . .

RUN mkdir -p /app/data /app/cache_store /app/exports /app/uploads

EXPOSE 9528

ENV PYTHONUNBUFFERED=1
ENV IPTV_CHECK_HOST=0.0.0.0
ENV IPTV_CHECK_PORT=9528

VOLUME ["/app/data", "/app/cache_store", "/app/exports"]

CMD ["python", "-m", "iptv_check.server.main"]
