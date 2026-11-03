"""Fail closed on engine readiness, then replace this process with Uvicorn."""
import json
import os
import sys

from src.katago_client import KataGoClient


def server_port() -> int:
    value = os.environ.get("PORT", "8080")
    try:
        port = int(value)
    except ValueError as exc:
        raise RuntimeError("PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("PORT must be between 1 and 65535")
    return port


def main() -> None:
    port = server_port()
    readiness = KataGoClient.from_environment().readiness()
    print(json.dumps({
        "event": "engine_ready",
        "release": os.environ.get("GO_REVIEW_RELEASE", "unreleased"),
        "engine": readiness["engine"],
        "version": readiness["version"],
        "model_id": readiness["model_id"],
        "model_sha256": readiness["model_sha256"],
    }, ensure_ascii=True), flush=True)
    os.execv(sys.executable, [
        sys.executable, "-m", "uvicorn", "app.production:app",
        "--host", "0.0.0.0", "--port", str(port),
        "--workers", "1", "--no-access-log",
    ])


if __name__ == "__main__":
    main()
