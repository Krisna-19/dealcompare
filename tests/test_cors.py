from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

ALLOWED_DEV_ORIGIN = "http://localhost:5173"
ALLOWED_PROD_ORIGIN = "https://dealcompare.in"
ALLOWED_RENDER_PROD_ORIGIN = "https://dealcompare.onrender.com"
DISALLOWED_ORIGIN = "https://evil.example"


def test_preflight_from_allowed_dev_origin_is_accepted():
    res = client.options(
        "/search",
        headers={
            "Origin": ALLOWED_DEV_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED_DEV_ORIGIN
    assert "GET" in res.headers["access-control-allow-methods"]


def test_preflight_from_allowed_production_origin_is_accepted():
    res = client.options(
        "/search",
        headers={
            "Origin": ALLOWED_PROD_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED_PROD_ORIGIN


def test_preflight_from_allowed_render_production_origin_is_accepted():
    res = client.options(
        "/search",
        headers={
            "Origin": ALLOWED_RENDER_PROD_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED_RENDER_PROD_ORIGIN


def test_preflight_from_disallowed_origin_is_rejected():
    res = client.options(
        "/search",
        headers={
            "Origin": DISALLOWED_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    # CORSMiddleware answers disallowed preflights with a bare 400 and
    # no allow-origin header, so the browser blocks the call.
    assert res.status_code == 400
    assert "access-control-allow-origin" not in res.headers


def test_simple_get_from_allowed_origin_gets_cors_headers():
    res = client.get("/", headers={"Origin": ALLOWED_DEV_ORIGIN})

    assert res.status_code == 200
    assert res.headers["access-control-allow-origin"] == ALLOWED_DEV_ORIGIN


def test_simple_get_from_disallowed_origin_gets_no_cors_headers():
    res = client.get("/", headers={"Origin": DISALLOWED_ORIGIN})

    # The request itself is served (CORS is a browser-enforced policy),
    # but without an allow-origin header the browser blocks reading it.
    assert res.status_code == 200
    assert "access-control-allow-origin" not in res.headers


def test_wildcard_origin_is_not_used():
    res = client.get("/", headers={"Origin": ALLOWED_DEV_ORIGIN})

    assert res.headers.get("access-control-allow-origin") != "*"


def test_credentials_are_not_advertised():
    res = client.options(
        "/search",
        headers={
            "Origin": ALLOWED_DEV_ORIGIN,
            "Access-Control-Request-Method": "GET",
        },
    )

    assert res.headers.get("access-control-allow-credentials") != "true"


def test_only_get_and_options_methods_are_allowed():
    res = client.options(
        "/search",
        headers={
            "Origin": ALLOWED_DEV_ORIGIN,
            "Access-Control-Request-Method": "POST",
        },
    )

    allowed = res.headers.get("access-control-allow-methods", "")
    assert allowed == "GET, OPTIONS"
