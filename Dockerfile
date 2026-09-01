# dealcompare-api - production image
#
# Multi-stage build so the runtime image never contains build tooling or the
# pip download cache.
#
# Base image is the official Playwright image pinned to the exact version in
# requirements.txt (1.62.0). It ships a Python runtime plus pre-installed
# Chromium and its OS libraries, so no `apt-get` and no separate browser
# download are needed at deploy time.
#
# Build:
#     docker build -t dealcompare-api .
# Run:
#     docker run --rm -p 8000:8000 -e PORT=8000 dealcompare-api

# --- Stage 1: wheels ----------------------------------------------------------
FROM python:3.13-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip wheel --wheel-dir /build/wheels -r requirements.txt

# --- Stage 2: runtime ---------------------------------------------------------
FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

WORKDIR /app

# mcr Playwright images run as root by default; we install deps as root, then
# drop privileges to a dedicated non-root user for serving.
COPY --from=builder /build/wheels /build/wheels
RUN pip install --no-index --find-links /build/wheels -r requirements.txt \
    && rm -rf /build/wheels

COPY app ./app
COPY affiliates ./affiliates

# Non-root runtime user with a writable HOME (Playwright/Chromium need it).
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

ENV HEADLESS_BROWSER=true \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Render injects PORT; locals fall back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]