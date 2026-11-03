from fastapi.testclient import TestClient
import pytest

from app.local import PROJECT_ID, app


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def test_frontend_and_api_share_one_origin(client):
    page = client.get("/")
    assert page.status_code == 200
    assert "围棋复盘" in page.text
    assert page.headers["cache-control"] == "no-store"
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/local-status").json() == {
        "application": "go-review-ai-local", "project_id": PROJECT_ID,
    }
    parsed = client.post("/api/v1/parse-sgf", files={
        "file": ("example.sgf", b"(;GM[1]FF[4]SZ[19]RU[Chinese]KM[7.5];B[pd])"),
    })
    assert parsed.status_code == 200


@pytest.mark.parametrize("path", [
    "/styles.css", "/game-settings.mjs", "/report-view.mjs", "/board-markers.mjs",
    "/icons/upload.svg", "/icons/undo-2.svg",
])
def test_local_assets_are_served_without_a_cdn(client, path):
    result = client.get(path)
    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    assert result.content


@pytest.mark.parametrize("path", ["/.git/config", "/.local/server.plist", "/config/analysis.cfg", "/src/main.py", "/archive/README.md"])
def test_checkout_private_and_archive_paths_are_not_published(client, path):
    assert client.get(path).status_code == 404
