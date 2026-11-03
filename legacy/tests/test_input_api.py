import json

import pytest
from fastapi.testclient import TestClient

from app.limits import BodyLimitMiddleware, MAX_REQUEST_BYTES
from app.main import create_app
from src.game import MAX_SGF_BYTES
from tests.mock_engine import MockEngineClient


@pytest.fixture
def api():
    calls = []

    def engine_factory():
        calls.append("engine created")
        return MockEngineClient()

    with TestClient(create_app(engine_factory)) as client:
        yield client, calls


def payload(**changes):
    data = {"board_size": 19, "rules": "chinese", "komi": 7.5,
            "moves": [{"color": "B", "sgf": "aa"}]}
    data.update(changes)
    return data


def upload(client, data, endpoint="parse-sgf", params=None):
    return client.post(f"/api/v1/{endpoint}", params=params,
                       files={"file": ("input.sgf", data, "application/x-go-sgf")})


def test_both_input_previews_match_and_do_not_start_engine(api):
    client, calls = api
    sgf = upload(client, b"(;SZ[19]RU[Chinese]KM[7.5]B[aa])")
    manual = client.post("/api/v1/validate-moves", json=payload())
    assert sgf.status_code == manual.status_code == 200
    assert sgf.json() == manual.json()
    assert sgf.json()["status"] == "ready"
    assert calls == []


def test_missing_metadata_preview_confirmation_and_analysis(api):
    client, calls = api
    data = b"(;SZ[19];B[aa])"
    preview = upload(client, data)
    assert preview.json()["missing_fields"] == ["rules", "komi"]
    assert preview.json()["status"] == "needs_metadata"
    rejected = upload(client, data, "analyze-sgf")
    assert rejected.status_code == 400
    assert rejected.json()["error"]["code"] == "missing_metadata"
    assert calls == []
    accepted = upload(client, data, "analyze-sgf", {"rules": "chinese", "komi": 0})
    assert accepted.status_code == 200
    assert accepted.json()["game_summary"]["rules"] == "chinese"
    assert accepted.json()["game_summary"]["komi"] == 0
    assert len(calls) == 1


@pytest.mark.parametrize("data", [
    b"bad", b"\xff", b"(;SZ[13];B[aa])", b"(;SZ[19]AB[aa];W[bb])",
    b"(;SZ[19]RU[Japanese]KM[6.5];B[aa];W[aa])",
    b"(;SZ[19]RU[Japanese]KM[6.5];W[aa])",
])
def test_invalid_sgf_never_creates_engine(api, data):
    client, calls = api
    response = upload(client, data, "analyze-sgf")
    assert response.status_code == 400
    assert response.json()["error"]["code"]
    assert calls == []


@pytest.mark.parametrize("change,status", [
    ({"rules": None}, 400), ({"komi": None}, 400), ({"rules": "aga"}, 422),
    ({"board_size": 13}, 400), ({"board_size": True}, 422), ({"board_size": "19"}, 422),
    ({"komi": True}, 422), ({"komi": "6.5"}, 422), ({"komi": .25}, 400),
    ({"limit": 0}, 422), ({"limit": 6}, 422), ({"limit": 501}, 422), ({"loss_threshold": -1}, 422),
    ({"severe_threshold": 2}, 400), ({"severe_threshold": -1}, 422),
    ({"moves": []}, 422), ({"moves": [{"color": "B"}]}, 422),
    ({"moves": [{"color": "B", "sgf": ""}]}, 400),
    ({"moves": [{"color": "B", "sgf": "aa"}, {"color": "W", "sgf": "aa"}]}, 400),
    ({"moves": [{"color": "B", "sgf": "aa"}] * 501}, 422),
    ({"handicap": 2}, 422), ({"players": {"black": "A" * 257}}, 422),
])
def test_invalid_manual_input_never_creates_engine(api, change, status):
    client, calls = api
    response = client.post("/api/v1/analyze-moves", json=payload(**change))
    assert response.status_code == status, response.text
    assert response.json()["error"]["code"]
    assert calls == []


@pytest.mark.parametrize("name", ["komi", "loss_threshold", "severe_threshold"])
@pytest.mark.parametrize("value", [float("nan"), float("inf"), -float("inf")])
def test_nonfinite_json_errors_are_serializable(api, name, value):
    client, calls = api
    response = client.post("/api/v1/analyze-moves", content=json.dumps(payload(**{name: value})),
                           headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert calls == []


@pytest.mark.parametrize("params", [
    {"loss_threshold": "nan"}, {"loss_threshold": "inf"}, {"loss_threshold": -1},
    {"limit": 0}, {"limit": 6}, {"limit": 501}, {"komi": "nan"}, {"rules": "aga"},
    {"severe_threshold": 2}, {"severe_threshold": "nan"}, {"severe_threshold": "inf"},
])
def test_invalid_sgf_options_never_create_engine(api, params):
    client, calls = api
    response = upload(client, b"(;SZ[19]RU[Japanese]KM[6.5];B[aa])", "analyze-sgf", params)
    assert response.status_code == 400
    assert calls == []


def test_limits_apply_to_raw_sgf_and_total_body(api):
    client, calls = api
    raw = b"(;SZ[19];B[aa])"
    exact = raw + b" " * (MAX_SGF_BYTES - len(raw))
    assert upload(client, exact).status_code == 200
    assert upload(client, exact + b" ").status_code == 413
    response = client.post("/api/v1/analyze-moves", content=b"x" * (MAX_REQUEST_BYTES + 1),
                           headers={"Origin": "http://localhost:3000"})
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
    assert calls == []


def test_chunked_limit_does_not_trust_content_length():
    import asyncio

    async def scenario():
        seen = []
        events = iter([
            {"type": "http.request", "body": b"x" * MAX_REQUEST_BYTES, "more_body": True},
            {"type": "http.request", "body": b"x", "more_body": False},
        ])

        async def receive():
            return next(events)

        async def send(event):
            seen.append(event)

        async def downstream(*_args):
            pytest.fail("Oversize data reached multipart/JSON parsing")

        await BodyLimitMiddleware(downstream)({"type": "http", "method": "POST"}, receive, send)
        assert seen[0]["status"] == 413

    asyncio.run(scenario())


def test_engine_failure_does_not_expose_local_paths():
    def failed_engine():
        raise RuntimeError("Cannot open /private/model/secret-config.cfg")

    client = TestClient(create_app(failed_engine))
    response = client.post("/api/v1/analyze-moves", json=payload())
    assert response.status_code == 503
    assert "secret-config" not in response.text
