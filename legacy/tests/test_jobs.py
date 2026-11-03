import threading
import time
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.jobs import JobError, JobManager, replay_preview
from app.main import create_app
from app.settings import allowed_origins
from src.game import GameMove, GameRecord
from src.engine_types import KataGoUnavailableError
from tests.mock_engine import MockEngineClient


GAME = GameRecord(19, 7.5, None, None, None, (GameMove("B", "aa"),), "chinese")


def wait_for(manager, job_id, states=("succeeded", "failed", "cancelled")):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = manager.get(job_id)
        if value["state"] in states:
            return value
        time.sleep(.005)
    pytest.fail(f"Job did not reach {states}")


class SlowEngine(MockEngineClient):
    def __init__(self):
        super().__init__()
        self.entered, self.released = threading.Event(), threading.Event()
        self.cleaned = False

    def configure_control(self, control):
        self.control = control

    def analyze_position(self, position):
        self.entered.set()
        try:
            while not self.released.wait(.005):
                self.control.checkpoint()
            self.control.advance(1, 2)
            return super().analyze_position(position)
        finally:
            self.cleaned = True


def test_capacity_cancel_cleanup_and_next_job():
    engine = SlowEngine()
    manager = JobManager(lambda: engine, queue_capacity=1)
    try:
        first = manager.submit(GAME)["id"]
        assert engine.entered.wait(1)
        second = manager.submit(GAME)["id"]
        assert manager.get(second)["queue_position"] == 1
        with pytest.raises(JobError, match="full") as error:
            manager.submit(GAME)
        assert error.value.status == 429
        assert manager.cancel(second)["state"] == "cancelled"
        replacement = manager.submit(GAME)["id"]
        assert manager.cancel(first)["cancel_requested"]
        assert wait_for(manager, first)["state"] == "cancelled"
        assert engine.cleaned
        engine.released.set()
        assert wait_for(manager, replacement)["state"] == "succeeded"
    finally:
        manager.close()


def test_deadline_failure_and_sanitized_errors():
    engine = SlowEngine()
    manager = JobManager(lambda: engine, timeout=.04)
    try:
        job = wait_for(manager, manager.submit(GAME)["id"])
        assert job["error"]["code"] == "analysis_timeout"
        assert job["result"] is None
        assert engine.cleaned
    finally:
        manager.close()
    def unavailable():
        raise KataGoUnavailableError("/private/secret/model")
    manager = JobManager(unavailable)
    try:
        job = wait_for(manager, manager.submit(GAME)["id"])
        assert job["error"]["code"] == "engine_unavailable"
        assert "/private" not in str(job)
    finally:
        manager.close()


def test_result_snapshot_progress_retention_and_restart():
    manager = JobManager(MockEngineClient, retention=.05)
    try:
        job_id = manager.submit(GAME)["id"]
        job = wait_for(manager, job_id)
        assert job["progress"] == {"completed": 2, "total": 2}
        assert job["result"]["schema_version"] == "3.0"
        job["result"].clear()
        assert manager.get(job_id)["result"]["schema_version"] == "3.0"
        assert manager.input(job_id)["game"]["moves"] == [{"color": "B", "sgf": "aa"}]
        time.sleep(.07)
        with pytest.raises(JobError) as error:
            manager.get(job_id)
        assert error.value.code == "job_unavailable"
    finally:
        manager.close()
    restarted = JobManager(MockEngineClient)
    try:
        with pytest.raises(JobError):
            restarted.get(job_id)
    finally:
        restarted.close()


def test_result_budget_and_shutdown():
    manager = JobManager(MockEngineClient, max_result_bytes=10)
    assert wait_for(manager, manager.submit(GAME)["id"])["error"]["code"] == "analysis_failed"
    manager.close()
    engine = SlowEngine()
    manager = JobManager(lambda: engine)
    manager.submit(GAME)
    assert engine.entered.wait(1)
    manager.submit(GAME)
    manager.close()
    assert engine.cleaned
    assert manager._thread is None
    with pytest.raises(JobError, match="stopping"):
        manager.submit(GAME)


def test_completed_store_is_bounded():
    manager = JobManager(MockEngineClient, max_results=1)
    try:
        first = manager.submit(GAME)["id"]
        wait_for(manager, first)
        second = manager.submit(GAME)["id"]
        wait_for(manager, second)
        with pytest.raises(JobError):
            manager.get(first)
    finally:
        manager.close()


def test_preview_snapshots_capture_pass_and_move_numbers():
    game = replace(GAME, moves=tuple(GameMove("B" if i % 2 == 0 else "W", point)
                                    for i, point in enumerate(["ab", "aa", "ba", None])))
    preview = replay_preview(game)
    assert len(preview["positions"]) == 5
    assert preview["positions"][2]["stones"][-1] == {"color": "W", "sgf": "aa", "move_number": 2}
    assert preview["positions"][4]["stones"] == [
        {"color": "B", "sgf": "ab", "move_number": 1},
        {"color": "B", "sgf": "ba", "move_number": 3}]
    assert preview["positions"][4]["next_player"] == "B"


def test_job_routes_validation_warning_snapshot_and_legacy_capacity():
    engine = SlowEngine()
    manager = JobManager(lambda: engine, queue_capacity=0)
    with TestClient(create_app(job_manager=manager)) as client:
        payload = GAME.to_dict()
        payload.pop("record_status")
        assert client.post("/api/v1/jobs", json={**payload, "moves": []}).status_code == 422
        response = client.post("/api/v1/jobs", json={**payload, "input_warnings": ["first_variation_only"]})
        assert response.status_code == 202
        assert response.headers["cache-control"] == "no-store"
        job_id = response.json()["id"]
        assert engine.entered.wait(1)
        assert client.get("/health").json() == {"status": "ok"}
        assert client.post("/api/v1/analyze-moves", json=payload).status_code == 429
        assert client.get("/ready").status_code == 429
        assert client.get(f"/api/v1/jobs/{job_id}/input").json()["warnings"] == ["first_variation_only"]
        assert client.get("/api/v1/jobs/missing").status_code == 404
        assert client.get(f"/api/v1/jobs/{job_id}").headers["cache-control"] == "no-store"
        assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 200
        assert wait_for(manager, job_id)["state"] == "cancelled"


@pytest.mark.parametrize("origin", ["*", "https://*", "http://example.org", "https://example.org/path",
                                    "https://user@example.org", "https://example.org?x=1", "https://example.org:0"])
def test_cors_rejects_non_exact_or_insecure_origins(monkeypatch, origin):
    import json
    monkeypatch.setenv("GO_REVIEW_ALLOWED_ORIGINS", json.dumps([origin]))
    with pytest.raises(ValueError):
        allowed_origins()


def test_cors_allows_only_configured_origin(monkeypatch):
    monkeypatch.setenv("GO_REVIEW_ALLOWED_ORIGINS", '["https://example.github.io"]')
    with TestClient(create_app(MockEngineClient)) as client:
        for origin, expected in [("https://example.github.io", 200), ("https://other.github.io", 400)]:
            response = client.options("/api/v1/jobs", headers={"Origin": origin,
                "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
            assert response.status_code == expected
        assert client.get("/health", headers={"Origin": "https://evil.test"}).headers.get("access-control-allow-origin") is None
