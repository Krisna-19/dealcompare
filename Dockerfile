# dealcompare-api - production image
#
# Single-stage build on the official Playwright Python image, pinned to the
# exact Playwright version in requirements.txt (1.62.0).  Using one base for
# both dependency install and runtime means:
#   - the app and `pip` run on the SAME Python (the image's apt Python 3.10),
#     avoiding ABI mismatches from building wheels on python:3.13-slim; and
#   - playwright==1.62.0 is re-installed so the baked-in Chromium revision
#     always matches the pinned package exactly.
#
# The base image already ships Chromium's OS libraries and sets
# PLAYWRIGHT_BROWSERS_PATH=/ms-playwright; we (re)install the browser into that
# same path during the build and verify it is present in the final image, so
# the runtime never falls back to Render's /opt/render/.cache/ms-playwright.
#
# Build:
#     docker build -t dealcompare-api .
# Run:
#     docker run --rm -p 8000:8000 -e PORT=8000 dealcompare-api

FROM mcr.microsoft.com/playwright/python:v1.62.0-jammy

# Deterministic browser location, used by both the build-time install and the
# runtime lookup.  The base image already sets this to the same value.
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app

# Runtime deps for the image's OWN Python runtime (installed from PyPI so the
# wheels match it).  --no-cache-dir keeps the image lean.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY affiliates ./affiliates
COPY docker-entrypoint.sh /app/docker-entrypoint.sh

# Install the Chromium browser (full + headless shell) that matches the pinned
# playwright==1.62.0 package.  The base image provides Chromium's OS libraries
# (no apt / --with-deps needed).  It writes to $PLAYWRIGHT_BROWSERS_PATH.
RUN python -m playwright install chromium \
    && python -c 'import pathlib; p=pathlib.Path("/ms-playwright"); rows=[x.name for x in p.iterdir()] if p.exists() else []; print("PLAYWRIGHT_BROWSERS_PATH contents:", sorted(rows)); missing=[b for b in ("chromium","chromium_headless_shell") if not any(r.startswith(b+"-") for r in rows)]; assert not missing, "Playwright browser(s) missing from image: %s" % missing; print("Playwright Chromium present in image: OK")'

# Non-root runtime user with a writable HOME (Playwright/Chromium need it).
RUN useradd --create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /app \
    && chmod +x /app/docker-entrypoint.sh

# Let the non-root runtime user read/browse the baked-in browser.
RUN chmod -R a+rX /ms-playwright

ENV HEADLESS_BROWSER=true \
    PYTHONUNBUFFERED=1

USER appuser
EXPOSE 8000

# Healthcheck is PORT-aware ($PORT is injected by Render; 8000 is the local default).
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT', '8000') + '/health')"

# Entrypoint runs the Playwright pre-flight (pins PLAYWRIGHT_BROWSERS_PATH,
# verifies the browser), then starts uvicorn bound to $PORT.
ENTRYPOINT ["/app/docker-entrypoint.sh"]