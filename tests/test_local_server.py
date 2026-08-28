import io
import json
from types import SimpleNamespace
import plistlib

import pytest

from scripts import local_server as server


def test_port_collision_chooses_a_free_loopback_port(monkeypatch):
    attempts = []

    class FakeSocket:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def bind(self, address):
            attempts.append(address)
            if address[1] == 3000:
                raise OSError("already in use")

        def setsockopt(self, level, option, value):
            assert (level, option, value) == (server.socket.SOL_SOCKET, server.socket.SO_REUSEADDR, 1)

    monkeypatch.setattr(server.socket, "socket", FakeSocket)
    assert server.available_port(3000) == 3001
    assert attempts == [("127.0.0.1", 3000), ("127.0.0.1", 3001)]


def test_config_is_loopback_only_and_does_not_install_login_startup(monkeypatch):
    monkeypatch.setattr(server, "engine_environment", lambda: {"KATAGO_PATH": "/example/katago"})
    config = server.service_config(3004)
    args = config["ProgramArguments"]
    assert args[args.index("--host") + 1] == "127.0.0.1"
    assert args[args.index("--port") + 1] == "3004"
    assert "app.local:app" in args
    assert config["WorkingDirectory"] == str(server.ROOT)
    assert "LaunchAgents" not in str(server.PLIST)
    assert server.PLIST.parent == server.ROOT / ".local"


def test_explicit_engine_configuration_is_preserved(monkeypatch):
    monkeypatch.setenv("KATAGO_PATH", "/custom/katago")
    monkeypatch.setenv("KATAGO_CONFIG_PATH", "/custom/config.cfg")
    monkeypatch.setenv("KATAGO_MODEL_PATH", "/custom/model.bin.gz")
    env = server.engine_environment()
    assert env["KATAGO_PATH"] == "/custom/katago"
    assert env["KATAGO_MODEL_PATH"] == "/custom/model.bin.gz"
    assert env["KATAGO_CONFIG_PATH"] == "/custom/config.cfg"


def test_repeated_start_is_idempotent(monkeypatch):
    monkeypatch.setattr(server, "loaded", lambda: True)
    monkeypatch.setattr(server, "saved_port", lambda: 3002)
    monkeypatch.setattr(server, "healthy", lambda port: port == 3002)
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **kw: pytest.fail("must not bootstrap twice"))
    assert server.start() == 3002


def test_unhealthy_loaded_job_is_not_replaced_silently(monkeypatch):
    monkeypatch.setattr(server, "loaded", lambda: True)
    monkeypatch.setattr(server, "saved_port", lambda: 3000)
    monkeypatch.setattr(server, "healthy", lambda port: False)
    with pytest.raises(RuntimeError, match="run restart"):
        server.start()


def test_stop_only_targets_this_checkout_job(monkeypatch):
    calls = []
    states = iter([True, True, False])
    monkeypatch.setattr(server, "loaded", lambda: next(states))
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    monkeypatch.setattr(server.subprocess, "run", lambda args, **kwargs: calls.append((args, kwargs)))
    server.stop()
    assert calls == [(["launchctl", "bootout", f"{server.DOMAIN}/{server.LABEL}"], {"check": True})]


def test_stop_wait_is_bounded(monkeypatch):
    monkeypatch.setattr(server, "loaded", lambda: True)
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **kw: None)
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    with pytest.raises(RuntimeError, match="still stopping"):
        server.stop()


def test_stop_when_already_stopped_is_a_noop(monkeypatch):
    monkeypatch.setattr(server, "loaded", lambda: False)
    monkeypatch.setattr(server.subprocess, "run", lambda *a, **kw: pytest.fail("must not stop other jobs"))
    server.stop()


def test_health_requires_the_exact_project_identity(monkeypatch):
    payload = {"application": "go-review-ai-local", "project_id": "another-checkout"}
    monkeypatch.setattr(server, "build_opener", lambda *a: SimpleNamespace(
        open=lambda *a, **kw: io.BytesIO(json.dumps(payload).encode())))
    assert not server.healthy(3000)
    payload["project_id"] = server.PROJECT_ID
    assert server.healthy(3000)
    assert not server.healthy(None)


def test_saved_port_rejects_a_different_job_identity(monkeypatch, tmp_path):
    plist = tmp_path / "server.plist"
    plist.write_bytes(plistlib.dumps({"Label": "another-job", "ProgramArguments": ["--port", "3000"]}))
    monkeypatch.setattr(server, "PLIST", plist)
    with pytest.raises(RuntimeError, match="identity"):
        server.saved_port()
