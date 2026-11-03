from pathlib import Path
import json
import subprocess
import sys

from scripts.container_server import server_port


ROOT = Path(__file__).resolve().parents[1]
MODEL_SHA = "9d7a6afed8ff5b74894727e156f04f0cd36060a24824892008fbb6e0cba51f1d"
SOURCE_SHA = "51b1a9b48053b0de910f44abf2cc95160de7b6d43bb22300e0b80ea0b3ed0ca8"


def test_container_pins_engine_model_bases_and_nonroot_runtime():
    dockerfile = (ROOT / "Dockerfile").read_text()

    assert dockerfile.count("FROM ") == 2
    assert dockerfile.count("@sha256:") == 2
    assert "ARG KATAGO_VERSION=1.16.4" in dockerfile
    assert MODEL_SHA in dockerfile
    assert SOURCE_SHA in dockerfile
    assert "KATAGO_MAX_VISITS=64" in dockerfile
    assert "USER app" in dockerfile
    assert "--no-access-log" in (ROOT / "scripts/container_server.py").read_text()


def test_public_machine_is_single_instance_always_on_and_two_gibibytes():
    config = (ROOT / "deploy/fly.toml").read_text()

    assert 'primary_region = "syd"' in config
    assert "auto_stop_machines = false" in config
    assert "min_machines_running = 1" in config
    assert 'size = "shared-cpu-2x"' in config
    assert 'memory = "2gb"' in config
    assert 'path = "/health"' in config
    assert 'wait_timeout = "10m"' in config
    assert 'GO_REVIEW_ALLOWED_ORIGINS = \'["https://yulinhenryou.github.io"]\'' in config


def test_model_license_and_private_runtime_exclusions_are_distributed():
    license_text = (ROOT / "licenses/KATAGO_NETWORK_LICENSE.txt").read_text()
    ignore = (ROOT / ".dockerignore").read_text().splitlines()

    assert "Copyright 2026 David J Wu" in license_text
    assert "kata1-b18c384nbt-s9996604416-d4316597426.bin.gz" in license_text
    assert {"models", "reports", "uploads", "analysis_logs"} <= set(ignore)


def test_frontend_is_compatible_with_the_public_content_security_policy():
    sources = "\n".join(path.read_text() for path in (ROOT / "frontend").glob("*.mjs"))
    html = (ROOT / "frontend/index.html").read_text()

    assert ' style="' not in sources
    assert "<style" not in html
    assert "onclick=" not in html


def test_pages_demo_is_explicit_and_built_from_real_engine_evidence(tmp_path):
    bundle = json.loads((ROOT / "frontend/demo-data.json").read_text())
    assert bundle["generated_from"] == "samples/m3_mistake.sgf"
    assert bundle["report"]["engine_source"] == "katago"
    assert bundle["report"]["schema_version"] == "3.0"
    assert len(bundle["input"]["positions"]) == len(bundle["input"]["game"]["moves"]) + 1

    output = tmp_path / "pages"
    subprocess.run([sys.executable, "scripts/build_pages.py", str(output)], check=True)
    html = (output / "index.html").read_text()
    assert '<script type="module" src="./demo-app.mjs"></script>' in html
    assert "KataGo 示例报告" in html
    assert (output / ".nojekyll").is_file()
    assert not (output / "app.mjs").exists()


def test_container_port_is_strict(monkeypatch):
    monkeypatch.setenv("PORT", "8080")
    assert server_port() == 8080
    for invalid in ("0", "65536", "eight"):
        monkeypatch.setenv("PORT", invalid)
        try:
            server_port()
        except RuntimeError:
            pass
        else:
            raise AssertionError(f"PORT={invalid} should fail")
