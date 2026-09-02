#!/bin/sh
set -eu

# Runtime pre-flight for the Playwright browser baked into this image.
#
# The Chromium browsers are installed into /ms-playwright at build time (see
# Dockerfile).  Against anything at runtime that tries to point Playwright
# elsewhere -- e.g. a PLAYWRIGHT_BROWSERS_PATH injected via the Render native
# runtime, which resolves to $HOME/.cache/ms-playwright =
# /opt/render/.cache/ms-playwright, a path that is not populated inside the
# container -- we force the path used during the build, deterministically.
export PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
echo "[entrypoint] PLAYWRIGHT_BROWSERS_PATH=$PLAYWRIGHT_BROWSERS_PATH"

# Fail fast if the browser directory tree is missing, and confirm Playwright
# itself resolves a real Chromium executable from that location.
python - "$PLAYWRIGHT_BROWSERS_PATH" <<'PY'
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
rows = sorted(p.name for p in root.iterdir()) if root.exists() else []
print("[entrypoint] browser dirs on disk:", rows)
required = ("chromium-", "chromium_headless_shell-")
missing = [b for b in required if not any(r.startswith(b) for r in rows)]
if missing:
    sys.stderr.write("FATAL: Playwright browser dirs missing: %s\n" % missing)
    sys.exit(1)

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    exe = pathlib.Path(p.chromium.executable_path)
    ok = exe.exists()
    print("[entrypoint] chromium executable: %s -> %s" % (exe, "OK" if ok else "MISSING"))
    if not ok:
        sys.stderr.write("FATAL: resolved Chromium executable does not exist: %s\n" % exe)
        sys.exit(1)
print("[entrypoint] Playwright Chromium pre-flight: OK")
PY

# Render injects PORT; locals fall back to 8000.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"