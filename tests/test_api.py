import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from app.main import create_app
from src.katago_client import MockEngineClient


def test_analyze_sgf_upload_returns_structured_review() -> None:
    app = create_app(engine_factory=lambda: MockEngineClient(candidate_count=3))
    client = TestClient(app)

    with open("samples/sample_game.sgf", "rb") as f:
        response = client.post(
            "/api/v1/analyze-sgf",
            files={"file": ("sample_game.sgf", f, "application/x-go-sgf")},
        )

    assert response.status_code == 200
    payload = response.json()

    assert payload["schema_version"] == "1.0"
    assert payload["game_summary"]["board_size"] == 19
    assert payload["game_summary"]["moves_analyzed"] == 4
    assert len(payload["selected_mistakes"]) == 3


def test_analyze_sgf_rejects_invalid_sgf() -> None:
    app = create_app(engine_factory=lambda: MockEngineClient(candidate_count=3))
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyze-sgf",
        files={"file": ("bad.sgf", b"not sgf", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert "Expected '('" in response.json()["detail"]


def test_analyze_sgf_rejects_non_utf8_upload() -> None:
    app = create_app(engine_factory=lambda: MockEngineClient(candidate_count=3))
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyze-sgf",
        files={"file": ("bad.sgf", b"\xff\xfe\xfa", "application/octet-stream")},
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "SGF file must be UTF-8 text"


def test_analyze_moves_returns_structured_review() -> None:
    app = create_app(engine_factory=lambda: MockEngineClient(candidate_count=3))
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyze-moves",
        json={
            "board_size": 19,
            "komi": 6.5,
            "players": {"black": "Lee Sedol", "white": "AlphaGo"},
            "moves": [
                {"color": "B", "sgf": "pd"},
                {"color": "W", "sgf": "dd"},
                {"color": "B", "sgf": "qp"},
                {"color": "W", "sgf": "dc"},
            ],
            "loss_threshold": 1.0,
            "limit": 2,
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["schema_version"] == "1.0"
    assert payload["game_summary"]["board_size"] == 19
    assert payload["game_summary"]["komi"] == 6.5
    assert payload["game_summary"]["players"] == {
        "black": "Lee Sedol",
        "white": "AlphaGo",
    }
    assert payload["game_summary"]["moves_analyzed"] == 4
    assert payload["game_summary"]["mistakes_reviewed"] == 2
    assert len(payload["selected_mistakes"]) == 2


def test_analyze_moves_rejects_out_of_range_coordinate() -> None:
    app = create_app(engine_factory=lambda: MockEngineClient(candidate_count=3))
    client = TestClient(app)

    response = client.post(
        "/api/v1/analyze-moves",
        json={
            "board_size": 9,
            "komi": 6.5,
            "moves": [
                {"color": "B", "sgf": "jj"},
            ],
        },
    )

    assert response.status_code == 400
    assert "Move out of board range" in response.json()["detail"]


def test_analyze_moves_allows_cors_from_localhost_3000() -> None:
    app = create_app(engine_factory=lambda: MockEngineClient(candidate_count=3))
    client = TestClient(app)

    response = client.options(
        "/api/v1/analyze-moves",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
