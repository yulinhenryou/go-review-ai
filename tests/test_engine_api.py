from dataclasses import replace

from fastapi.testclient import TestClient

from app.main import create_app
from tests.mock_engine import MockEngineClient


def test_default_api_has_no_simulated_fallback(monkeypatch):
    monkeypatch.delenv("KATAGO_MODEL_PATH", raising=False)
    monkeypatch.delenv("KATAGO_CONFIG_PATH", raising=False)
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.get("/ready").status_code == 503
    response = client.post("/api/v1/analyze-moves", json={
        "board_size": 19, "komi": 6.5, "rules": "japanese", "moves": [{"color": "B", "sgf": "pd"}],
    })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "engine_unavailable"
    assert "timeline" not in response.json()


def test_incomplete_evidence_cannot_be_presented_as_a_complete_report():
    class IncompleteEngine(MockEngineClient):
        def analyze_position(self, position):
            return replace(super().analyze_position(position), played_winrate=None)
    client = TestClient(create_app(engine_factory=IncompleteEngine))
    response = client.post("/api/v1/analyze-moves", json={
        "board_size": 19, "komi": 6.5, "rules": "japanese", "moves": [{"color": "B", "sgf": "pd"}],
    })
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "incomplete_analysis"


def test_timeline_has_fixed_black_perspective():
    client = TestClient(create_app(engine_factory=MockEngineClient))
    response = client.post("/api/v1/analyze-moves", json={
        "board_size": 19, "komi": 6.5, "rules": "japanese",
        "moves": [{"color": "B", "sgf": "pd"}, {"color": "W", "sgf": "dd"}],
    })
    value = response.json()
    assert value["engine_source"] == "unverified_test_double"
    for item in value["timeline"]:
        sign = 1 if item["color"] == "B" else -1
        assert item["score_black_after"] == sign * item["score_after"]
        assert item["winrate_black_after"] == (item["winrate_after"] if sign == 1 else 1 - item["winrate_after"])
