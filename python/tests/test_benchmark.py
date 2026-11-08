"""The benchmark tool's plumbing, with the fake engine (no real numbers)."""

from __future__ import annotations

import json
import shlex
import sys
from pathlib import Path

import pytest

from weiqi.tools.benchmark import main, warmup_request
from weiqi.tools.record_engine import PUBLIC_SGF_DIR, load_record, request_for_record

FAKE = Path(__file__).parent / "engine" / "fake_katago.py"
GAME = PUBLIC_SGF_DIR / "synthetic-short.sgf"


def test_the_report_covers_every_scenario_without_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    launcher = tmp_path / "katago"
    launcher.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} normal "$@"\n'
    )
    launcher.chmod(0o755)
    (tmp_path / "model.bin.gz").write_bytes(b"fixture model")
    (tmp_path / "analysis.cfg").write_text("fixture config\n")
    monkeypatch.setenv("KATAGO_PATH", str(launcher))
    monkeypatch.setenv("KATAGO_MODEL_PATH", str(tmp_path / "model.bin.gz"))
    monkeypatch.setenv("KATAGO_CONFIG_PATH", str(tmp_path / "analysis.cfg"))
    output = tmp_path / "report.json"

    assert main([str(GAME), "--visits", "8", "16", "--output", str(output)]) == 0
    text = output.read_text()
    report = json.loads(text)
    assert report["game"]["sgf"] == "testdata/sgf/synthetic-short.sgf"
    scenarios = [(run["visits"], run["mode"]) for run in report["runs"]]
    assert scenarios == [(8, "cold"), (8, "warm"), (16, "cold"), (16, "warm")]
    for run in report["runs"]:
        assert run["positions"] == 7
        assert run["analysis_seconds"] > 0
        assert run["engine_peak_rss_bytes"] > 0 and run["worker_peak_rss_bytes"] > 0
        assert ("startup_seconds" in run) == (run["mode"] == "cold")
        assert ("cache_seconds" in run) == (run["mode"] == "warm")
    assert str(tmp_path) not in text and "/Users/" not in text


def test_the_warmup_position_is_not_in_the_game() -> None:
    game = request_for_record(load_record(GAME), rules="japanese", komi=6.5, max_visits=8)
    warmup = warmup_request(19, 19, "japanese", 6.5)
    assert warmup.hashes[0] not in game.hashes
