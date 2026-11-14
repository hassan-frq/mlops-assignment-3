# Dockerfile — Flask + Gunicorn image for the BTC-USD forecast API
# Multi-stage build: builder installs deps, final image is slim.

# ---- builder ---------------------------------------------------------------
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ---- runtime ---------------------------------------------------------------
FROM python:3.11-slim

LABEL org.opencontainers.image.title="btc-forecast-api" \
      org.opencontainers.image.description="BTC-USD 7-day forecast Flask API" \
      org.opencontainers.image.source="https://github.com/hassan-frq/mlops-assignment-3"

# Non-root user for security
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application source
COPY app/        ./app/
COPY gunicorn.conf.py .
COPY tests/fixtures/ ./tests/fixtures/

# Shared model directory /app/models (PVC in Kubernetes / volume in Compose)
RUN mkdir -p /app/models && chown appuser:appgroup /app/models

USER appuser

EXPOSE 5000

# Falls back to the bundled sample fixture if this file does not exist yet.
ENV MODEL_ARTIFACT_PATH="/app/models/forecast.json"

# Health-check using the /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:5000/health')"

CMD ["gunicorn", "--config", "gunicorn.conf.py", "app.app:create_app()"]

