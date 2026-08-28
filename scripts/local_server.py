"""Start/stop an on-demand macOS user service; never install login startup."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ID = hashlib.sha256(str(ROOT).encode()).hexdigest()[:12]
LABEL = f"com.go-review.local.{PROJECT_ID}"
DOMAIN = f"gui/{os.getuid()}"
STATE = ROOT / ".local"
PLIST = STATE / "server.plist"
DEFAULT_MODEL = "kata1-b18c384nbt-s9996604416-d4316597426.bin.gz"


def available_port(start=3000):
    for port in range(start, start + 10):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free local port in the requested range")


def engine_environment():
    env = {"PATH": os.environ.get("PATH", "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin")}
    installed_binary = next((str(p) for p in
                             (Path("/opt/homebrew/bin/katago"), Path("/usr/local/bin/katago"))
                             if p.is_file()), "katago")
    env["KATAGO_PATH"] = os.environ.get("KATAGO_PATH") or shutil.which("katago") or installed_binary
    env["KATAGO_CONFIG_PATH"] = os.environ.get("KATAGO_CONFIG_PATH", str(ROOT / "config/analysis.cfg"))
    model = os.environ.get("KATAGO_MODEL_PATH")
    if not model:
        model = next((str(p) for prefix in ("/opt/homebrew", "/usr/local")
                      if (p := Path(prefix) / "share/katago" / DEFAULT_MODEL).is_file()), None)
    if model:
        env["KATAGO_MODEL_PATH"] = model
    for key in ("GO_REVIEW_QUEUE_CAPACITY", "GO_REVIEW_JOB_TIMEOUT", "GO_REVIEW_RESULT_TTL", "GO_REVIEW_ALLOWED_ORIGINS"):
        if key in os.environ:
            env[key] = os.environ[key]
    return env


def service_config(port):
    return {
        "Label": LABEL,
        "ProgramArguments": [str(ROOT / ".venv/bin/python"), "-m", "uvicorn", "app.local:app",
                             "--host", "127.0.0.1", "--port", str(port), "--no-access-log"],
        "WorkingDirectory": str(ROOT), "EnvironmentVariables": engine_environment(),
        "RunAtLoad": True, "KeepAlive": {"SuccessfulExit": False}, "ThrottleInterval": 10,
        "StandardOutPath": str(STATE / "server.log"), "StandardErrorPath": str(STATE / "server.log"),
    }


def loaded():
    return subprocess.run(["launchctl", "print", f"{DOMAIN}/{LABEL}"], capture_output=True).returncode == 0


def saved_port():
    if not PLIST.is_file():
        return None
    config = plistlib.loads(PLIST.read_bytes())
    if config.get("Label") != LABEL:
        raise RuntimeError("Unexpected local service identity")
    args = config["ProgramArguments"]
    return int(args[args.index("--port") + 1])


def healthy(port):
    if port is None:
        return False
    try:
        with build_opener(ProxyHandler({})).open(f"http://127.0.0.1:{port}/local-status", timeout=1) as response:
            return json.load(response) == {"application": "go-review-ai-local", "project_id": PROJECT_ID}
    except (OSError, ValueError):
        return False


def start(port=3000):
    if loaded():
        port = saved_port()
        if healthy(port):
            return port
        raise RuntimeError("Local service is loaded but unavailable; run restart and check .local/server.log")
    if not (ROOT / ".venv/bin/python").is_file():
        raise RuntimeError("Create .venv and install project dependencies first; see README")
    port = available_port(port)
    STATE.mkdir(mode=0o700, exist_ok=True)
    PLIST.write_bytes(plistlib.dumps(service_config(port)))
    PLIST.chmod(0o600)
    subprocess.run(["launchctl", "bootstrap", DOMAIN, str(PLIST)], check=True)
    for _ in range(40):
        if healthy(port):
            return port
        time.sleep(.25)
    stop()
    raise RuntimeError("Local service failed to start; check .local/server.log")


def stop():
    if loaded():
        subprocess.run(["launchctl", "bootout", f"{DOMAIN}/{LABEL}"], check=True)
        # bootout can return before launchd has finished unregistering the job.
        for _ in range(40):
            if not loaded():
                return
            time.sleep(.25)
        raise RuntimeError("Local service is still stopping; retry after it exits")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "restart", "status"])
    parser.add_argument("--port", type=int, default=3000)
    parser.add_argument("--open", action="store_true")
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("Use python -m uvicorn app.local:app --host 127.0.0.1 --port 3000 on other POSIX systems")
    if not 1024 <= args.port <= 65526:
        parser.error("port must be between 1024 and 65526")
    if args.action in {"stop", "restart"}:
        stop()
    if args.action == "stop":
        print("Local service stopped.")
        return
    if args.action == "status":
        port = saved_port()
        print(f"Running: http://localhost:{port}/" if loaded() and healthy(port) else "Stopped")
        return
    port = start(args.port)
    url = f"http://localhost:{port}/"
    print(url)
    print("On-demand background service; no login startup installed. Use stop to end it.")
    if args.open:
        webbrowser.open(url)


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
