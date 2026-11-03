import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from app.public import PublicProtectionMiddleware, SlidingWindowLimit, build_production_app
from app.settings import public_options
from tests.mock_engine import MockEngineClient


class ReadyEngine(MockEngineClient):
    def readiness(self):
        return {"status": "ready", "engine": "katago"}


def options(**overrides):
    values = {
        "hosts": ("testserver",),
        "release": "a" * 40,
        "client_ip_header": "fly-client-ip",
        "rate_window": 60,
        "client_limit": 2,
        "global_limit": 3,
    }
    values.update(overrides)
    return values


def test_sliding_window_enforces_client_and_global_limits():
    now = [100.0]
    limiter = SlidingWindowLimit(
        window=10, client_limit=2, global_limit=3, clock=lambda: now[0],
    )

    assert limiter.admit(b"client-a") == (True, 0)
    assert limiter.admit(b"client-a") == (True, 0)
    assert limiter.admit(b"client-a") == (False, 10)
    assert limiter.admit(b"client-b") == (True, 0)
    assert limiter.admit(b"client-c") == (False, 10)

    now[0] = 110.0
    assert limiter.admit(b"client-a") == (True, 0)


def test_public_app_hides_docs_validates_host_and_sets_security_headers():
    app = build_production_app(ReadyEngine, options=options())
    with TestClient(app) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/openapi.json").status_code == 404
        rejected = client.get("/release", headers={"Host": "wrong.example"})
        assert rejected.status_code == 400
        assert rejected.json()["error"]["code"] == "invalid_host"

        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers["content-security-policy"].startswith("default-src 'self'")
        assert response.headers["strict-transport-security"] == "max-age=31536000"
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["cache-control"] == "no-store"


def test_public_app_rejects_duplicate_host_headers():
    app = build_production_app(ReadyEngine, options=options())
    with TestClient(app) as client:
        response = client.get("/release", headers=[("Host", "testserver"), ("Host", "wrong.example")])

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_host"


def test_public_rate_limit_uses_trusted_client_header_without_retaining_raw_address():
    app = build_production_app(ReadyEngine, options=options())
    with TestClient(app) as client:
        headers = {"Fly-Client-IP": "203.0.113.7"}
        assert client.get("/ready", headers=headers).status_code == 200
        assert client.get("/ready", headers=headers).status_code == 200
        limited = client.get("/ready", headers=headers)
        assert limited.status_code == 429
        assert limited.json()["error"]["code"] == "rate_limited"
        assert limited.headers["retry-after"] == "60"

        assert client.get("/ready", headers={"Fly-Client-IP": "203.0.113.8"}).status_code == 200
        globally_limited = client.get("/ready", headers={"Fly-Client-IP": "203.0.113.9"})
        assert globally_limited.status_code == 429

    middleware = next(item for item in app.user_middleware if item.cls.__name__ == "PublicProtectionMiddleware")
    assert middleware.kwargs["client_ip_header"] == "fly-client-ip"
    instance = app.middleware_stack
    while not isinstance(instance, PublicProtectionMiddleware):
        instance = instance.app
    assert b"203.0.113.7" not in instance.limiter.client_events
    assert all(len(key) == 16 for key in instance.limiter.client_events)


def test_public_release_metadata_and_frontend_share_one_origin():
    app = build_production_app(ReadyEngine, options=options())
    with TestClient(app) as client:
        release = client.get("/release")
        assert release.json() == {
            "application": "go-review-ai",
            "release": "a" * 40,
            "storage": "ephemeral-memory",
            "engine": "real-katago",
        }
        assert client.get("/").status_code == 200


def test_public_options_require_explicit_mode_and_exact_hosts(monkeypatch):
    monkeypatch.delenv("GO_REVIEW_PUBLIC", raising=False)
    with pytest.raises(ValueError, match="GO_REVIEW_PUBLIC=1"):
        public_options()

    monkeypatch.setenv("GO_REVIEW_PUBLIC", "1")
    monkeypatch.setenv("GO_REVIEW_PUBLIC_HOSTS", json.dumps(["Review.Example"]),)
    with pytest.raises(ValueError, match="exact lowercase"):
        public_options()

    monkeypatch.setenv("GO_REVIEW_PUBLIC_HOSTS", json.dumps(["review.example"]),)
    monkeypatch.setenv("GO_REVIEW_RELEASE", "abc")
    with pytest.raises(ValueError, match="full lowercase Git commit"):
        public_options()


def test_public_options_can_derive_fly_hostname(monkeypatch):
    monkeypatch.setenv("GO_REVIEW_PUBLIC", "1")
    monkeypatch.delenv("GO_REVIEW_PUBLIC_HOSTS", raising=False)
    monkeypatch.setenv("FLY_APP_NAME", "go-review-syd")
    monkeypatch.setenv("GO_REVIEW_RELEASE", "b" * 40)
    monkeypatch.setenv("GO_REVIEW_CLIENT_IP_HEADER", "fly-client-ip")

    selected = public_options()

    assert selected["hosts"] == ("go-review-syd.fly.dev",)
    assert selected["client_ip_header"] == "fly-client-ip"


def test_public_fly_options_require_a_release_commit(monkeypatch):
    monkeypatch.setenv("GO_REVIEW_PUBLIC", "1")
    monkeypatch.setenv("FLY_APP_NAME", "go-review-syd")
    monkeypatch.delenv("GO_REVIEW_RELEASE", raising=False)

    with pytest.raises(ValueError, match="identify the source commit"):
        public_options()
