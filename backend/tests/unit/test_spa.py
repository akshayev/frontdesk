"""SPA serving rules (app/spa.py, D-037): API paths never swallowed, hashed assets cached
forever, index.html never cached, the strict CSP on every page. No database needed."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.security.headers import SECURITY_HEADERS

INDEX = "<!doctype html><title>Frontdesk</title><div id=root></div>"
CSP = dict(SECURITY_HEADERS)["Content-Security-Policy"]


@pytest.fixture
def built(tmp_path: Path) -> Path:
    """A fake `npm run build` output, plus a secret file next to (outside) it."""
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(INDEX)
    (root / "assets" / "index-Ab12Cd.js").write_text("console.log('app')")
    (root / "favicon.svg").write_text("<svg/>")
    (tmp_path / "secret.txt").write_text("do not serve")
    return root


@pytest.fixture
def client(built: Path) -> TestClient:
    return TestClient(create_app(Settings(static_dir=str(built))))


@pytest.mark.parametrize("path", ["/", "/login", "/tickets/3f1c/anything", "/t", "/new",
                                  "/reports/late", "/apidocs"])
def test_client_routes_get_index_html_uncached(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 200
    assert resp.text == INDEX
    assert resp.headers["content-type"].startswith("text/html")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["content-security-policy"] == CSP


def test_hashed_assets_are_immutable(client: TestClient) -> None:
    resp = client.get("/assets/index-Ab12Cd.js")
    assert resp.status_code == 200 and resp.text == "console.log('app')"
    assert resp.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert "javascript" in resp.headers["content-type"]
    assert resp.headers["content-security-policy"] == CSP


def test_missing_asset_is_404_not_index(client: TestClient) -> None:
    resp = client.get("/assets/gone-123.js")
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_top_level_file_served_uncached(client: TestClient) -> None:
    resp = client.get("/favicon.svg")
    assert resp.status_code == 200 and resp.text == "<svg/>"
    assert resp.headers["cache-control"] == "no-cache"


@pytest.mark.parametrize("path", ["/api", "/api/", "/api/nope", "/api/agent/unknown/x",
                                  "/openapi.json/x", "/healthz/x"])
def test_unknown_api_paths_are_json_404(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert resp.status_code == 404
    assert set(resp.json()) == {"error", "message", "request_id"}
    assert resp.headers["content-type"].startswith("application/json")
    assert resp.headers["content-security-policy"] == CSP


def test_api_healthz_and_openapi_are_not_swallowed(client: TestClient) -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
    schema = client.get("/openapi.json").json()
    assert "/api/agent/tickets" in schema["paths"]
    # The catch-alls are not part of the API contract.
    assert not {"/{path}", "/api", "/api/{path}"} & set(schema["paths"])
    # A real API route still answers as the API (401 JSON), not with index.html.
    resp = client.get("/api/auth/me")
    assert resp.status_code == 401 and resp.json()["error"]


@pytest.mark.parametrize("method", ["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.parametrize("path", ["/api", "/api/public/nope", "/api/customer/x/y",
                                  "/api/agent/tickets/1/2/3/4"])
def test_unknown_api_path_is_404_for_every_method(client: TestClient, method: str,
                                                  path: str) -> None:
    """Every unknown API path answers the same way, whatever the method (CSRF header sent, as
    the app always does; without it /api/agent|lead|auth writes are refused first with 403)."""
    resp = client.request(method, path, headers={"X-Requested-With": "frontdesk"})
    assert resp.status_code == 404
    assert set(resp.json()) == {"error", "message", "request_id"}
    assert resp.json()["error"] == "not_found"
    assert resp.headers["content-security-policy"] == CSP


@pytest.mark.parametrize(("method", "path", "allow"), [
    ("DELETE", "/api/agent/tickets", "GET, POST"),
    ("PUT", "/api/public/tickets", "POST"),
    ("POST", "/api/auth/me", "GET"),
])
def test_known_api_path_wrong_method_is_405(client: TestClient, method: str, path: str,
                                            allow: str) -> None:
    resp = client.request(method, path, headers={"X-Requested-With": "frontdesk"})
    assert resp.status_code == 405
    assert resp.json()["error"] == "method_not_allowed"
    assert resp.headers["allow"] == allow


def test_csv_endpoints_are_declared_text_csv(client: TestClient) -> None:
    """The OpenAPI contract says what the server really sends (generated frontend types)."""
    paths = client.get("/openapi.json").json()["paths"]
    for path in ("/api/agent/tickets/{ticket_id}/transcript.csv", "/api/lead/reports/late.csv"):
        content = paths[path]["get"]["responses"]["200"]["content"]
        assert list(content) == ["text/csv"]


@pytest.mark.parametrize("path", ["/assets/%2e%2e/%2e%2e/secret.txt", "/%2e%2e/secret.txt",
                                  "/assets/..%2F..%2Fsecret.txt"])
def test_no_path_traversal(client: TestClient, path: str) -> None:
    resp = client.get(path)
    assert "do not serve" not in resp.text


def test_without_a_build_the_api_still_works(tmp_path: Path) -> None:
    client = TestClient(create_app(Settings(static_dir=str(tmp_path / "missing"))))
    assert client.get("/healthz").status_code == 200
    resp = client.get("/tickets")
    assert resp.status_code == 404 and resp.json()["error"] == "not_found"


@pytest.mark.parametrize("path", ["/healthz", "/", "/tickets/3f1c", "/assets/index-Ab12Cd.js",
                                  "/openapi.json"])
def test_head_is_answered_like_get(client: TestClient, path: str) -> None:
    """Uptime monitors (UptimeRobot) send HEAD by default: same status as GET, no body."""
    resp = client.head(path)
    assert resp.status_code == 200 and resp.content == b""
    assert resp.headers["content-security-policy"] == CSP


@pytest.mark.parametrize("path", ["/docs", "/docs/oauth2-redirect", "/redoc"])
def test_swagger_paths_are_json_404_in_production(built: Path, path: str) -> None:
    """D-035: no Swagger UI in production, and its paths are not answered by the SPA either."""
    client = TestClient(create_app(Settings(static_dir=str(built), app_env="production")))
    resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["error"] == "not_found"


def test_swagger_ui_still_served_in_development(client: TestClient) -> None:
    assert client.get("/docs").status_code == 200
    assert "swagger" in client.get("/docs").text.lower()
