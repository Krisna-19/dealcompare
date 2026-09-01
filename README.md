# DealCompare API

Product price comparison API: scrapes Amazon, Flipkart, Myntra and Ajio for a
query, groups identical products across marketplaces, ranks them, and returns
the best deal with affiliate-tagged offer links.

## Repository layout

| Path | What it is |
|---|---|
| `app/` | FastAPI application (`main.py`), scrapers, aggregation/ranking services, config, error contract, metrics. |
| `affiliates/` | Affiliate link helpers (used by tests and response enrichment). |
| `tests/` | Deterministic pytest suite (live/network tests are tagged `live` and deselected by default). |
| `frontend/` | Lightweight vanilla-JS frontend + static server for local use. |
| `dealcompare-ui/` | React (Vite) frontend — the production UI. |
| `requirements.txt` / `requirements-dev.txt` | Pinned runtime / test dependencies. |
| `Dockerfile`, `render.yaml` | Containerization + Render blueprint. |
| `.github/workflows/ci.yml` | GitHub Actions: backend tests, UI lint/build, Docker image build. |

## Quickstart

```bash
# 1. Environment
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt
python -m playwright install chromium

# 2. Run the API
uvicorn app.main:app --reload        # http://127.0.0.1:8000

# 3. Optional: vanilla frontend on the CORS-allowed port
python frontend/serve.py             # http://127.0.0.1:5500

# 4. Optional: React UI (dev)
cd dealcompare-ui && npm ci && npm run dev   # http://localhost:5173
```

Configuration is environment-driven — copy `.env.example` to `.env` and adjust,
or set variables directly. Every setting has a safe default (see
`app/core/config.py`).

## Endpoints

| Endpoint | Description |
|---|---|
| `GET /` | Service banner. |
| `GET /health` | Liveness probe (rate-limit exempt). |
| `GET /metrics` | Prometheus text-format metrics (rate-limit exempt, no extra deps). |
| `GET /search?query=...` | `{message, category, results}` — see error contract below. |

Error responses use a stable envelope:
`{"detail": {"error": "<code>", "message": "<safe message>"}}` with codes
`invalid_query` (422), `rate_limited` (429), `upstream_scrape_failed` (502),
`internal_error` (500).

## Tests

```bash
python -m pytest -q                 # deterministic suite (live tests deselected)
python -m pytest -m live            # opt-in network/Amazon smoke tests
node frontend/tests/app.test.js     # vanilla frontend regression tests
cd dealcompare-ui && npm run lint && npm run build
```

## Docker & deployment

```bash
docker build -t dealcompare-api .
docker run --rm -p 8000:8000 -e PORT=8000 dealcompare-api
```

The image is based on the official Playwright image pinned to the version in
`requirements.txt`, so Chromium + its OS libraries are present at runtime and
no apt/browser download happens at deploy time.

`render.yaml` declares the production web service (`dealcompare-backend` on the
free plan, container runtime, `/health` probe). Deploying via Render containers
replaces the earlier Python buildpack. Secrets live in the Render dashboard, not
in the repo.

### Scaling note

The search cache, per-IP rate limiter and scrape-concurrency gate are
**in-memory and per-process**. Run exactly one worker/instance per deployment
(uvicorn's default). Horizontal scaling requires a shared store (e.g. Redis) and
is intentionally out of scope here.

## Repository hygiene

- Only the root `app/` tree is live. The old duplicated `dealcompare-api/*`
  subtree and every tracked `*.pyc` were removed; everything is recoverable from
  git history if ever needed.
- `seed_data.py` and other dead artifacts were removed; nothing imports them.