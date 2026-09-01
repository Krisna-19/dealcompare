# dealcompare-api - production image
#
# Multi-stage build so the runtime image never contains build tooling or the
# pip download cache.
#
# Base image is the official Playwright image pinned to the exact version in
# requirements.txt (1.62.0). It ships a Python runtime plus Chromium's OS
# libraries. We deliberately (re)install the Playwright browser during the
# build so the installed Chromium revision is guaranteed to match the pinned
# playwright==1.62.0 package (chromium / chromium-headless-shell v1234), and we
# pin PLAYWRIGHT_BROWSERS_PATH so the runtime looks in the same place the build
# wrote -- independent of any Render/injected cache path.
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

# Pin the Playwright browser install + lookup path to a single well-known
# location so the runtime package finds the exact browser baked into this image.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# mcr Playwright images run as root by default; we install deps as root, then
# drop privileges to a dedicated non-root user for serving.
COPY --from=builder /build/wheels /build/wheels
RUN pip install --no-index --find-links /build/wheels -r requirements.txt \
    && rm -rf /build/wheels

COPY app ./app
COPY affiliates ./affiliates

# Install the Chromium browser (full + headless shell) that matches the pinned
# playwright==1.62.0 package installed above, using the curated base image's
# pre-installed OS libraries (so no apt / --with-deps needed). The install
# writes to $PLAYWRIGHT_BROWSERS_PATH because that env is set above.
RUN python -m playwright install chromium \
    && python -c 'import pathlib; p=pathlib.Path("/ms-playwright"); rows=[x.name for x in p.iterdir()] if p.exists() else []; print("PLAYWRIGHT_BROWSERS_PATH contents:", sorted(rows)); missing=[b for b in ("chromium","chromium_headless_shell") if not any(r.startswith(b+"-") for r in rows)]; assert not missing, "Playwright browser(s) missing from image: %s" % missing; print("Playwright Chromium present in image: OK")'

# Non-root runtime user with a writable HOME (Playwright/Chromium need it).
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app

# Let the non-root runtime user read the baked-in browser and write browser
# sub-process state under it if needed.
RUN chmod -R a+rX /ms-playwright

ENV HEADLESS_BROWSER=true \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health')"

# Render injects PORT; locals fall back to 8000.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]