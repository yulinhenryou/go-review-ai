"""The review command line with the fake engine (a test double; the live run
against real KataGo is in `tests/live/`): exit codes, input errors before
any engine work, stored runs, and a cached second review."""

from __future__ import annotations

import io
import json
import shlex
import sys
from pathlib import Path

import pytest

from weiqi.review.cli import ENGINE_ERROR, INPUT_ERROR, main
from weiqi.tools.record_engine import REPO_ROOT

FAKE = Path(__file__).parents[1] / "engine" / "fake_katago.py"
CORPUS = REPO_ROOT / "testdata" / "sgf"
SGF = b"(;FF[4]GM[1]SZ[19]RU[Chinese]KM[7.5]PB[Alice]PW[Bob];B[pd];W[dd];B[pp];W[])"


def fake_environment(tmp_path: Path) -> dict[str, str]:
    launcher = tmp_path / "katago"
    launcher.write_text(
        f'#!/bin/sh\nexec {shlex.quote(sys.executable)} {shlex.quote(str(FAKE))} normal "$@"\n'
    )
    launcher.chmod(0o755)
    model, config = tmp_path / "model.bin.gz", tmp_path / "analysis.cfg"
    model.write_bytes(b"fixture model")
    config.write_text("fixture config\n")
    return {
        "KATAGO_PATH": str(launcher),
        "KATAGO_MODEL_PATH": str(model),
        "KATAGO_CONFIG_PATH": str(config),
    }


def run(tmp_path: Path, *args: str, environ: dict[str, str] | None = None) -> tuple[int, str, str]:
    stdout, stderr = io.StringIO(), io.StringIO()
    database = f"sqlite:///{tmp_path / 'weiqi.db'}"
    code = main(
        [*args, "--database", database, "--visits", "8"],
        environ=fake_environment(tmp_path) if environ is None else environ,
        stdout=stdout,
        stderr=stderr,
    )
    return code, stdout.getvalue(), stderr.getvalue()


def test_a_review_is_printed_stored_and_then_served_from_the_cache(tmp_path: Path) -> None:
    game = tmp_path / "game.sgf"
    game.write_bytes(SGF)
    code, out, err = run(tmp_path, str(game), "--format", "json")
    assert code == 0
    result = json.loads(out)
    assert result["schema"] == "review.v1"
    # The fake engine gives no score lead and no ownership: an honest partial result.
    assert result["status"] == "partial"
    assert result["coverage"]["missing_score_moves"] == [1, 2, 3, 4]
    assert "turns from the engine" in err and ", 0 from the cache" in err

    code, out, err = run(tmp_path, str(game), "--locale", "en")
    assert code == 0
    assert out.startswith("Game review\n")
    assert "Moves without score evidence: 1, 2, 3, 4" in out
    assert " 0 turns from the engine" in err


def test_the_report_can_be_written_to_a_file(tmp_path: Path) -> None:
    game, output = tmp_path / "game.sgf", tmp_path / "report.txt"
    game.write_bytes(SGF)
    code, out, _ = run(tmp_path, str(game), "--output", str(output))
    assert code == 0 and out == ""
    assert output.read_text(encoding="utf-8").startswith("复盘报告\n")


@pytest.mark.parametrize(
    ("name", "extra", "message"),
    [
        ("m4-missing-metadata.sgf", [], "metadata_unconfirmed"),
        ("m4-missing-metadata.sgf", ["--rules", "chinese"], "use --komi"),
        ("m4-invalid.sgf", [], "occupied"),
    ],
)
def test_inputs_that_cannot_be_reviewed_stop_before_the_engine(
    tmp_path: Path, name: str, extra: list[str], message: str
) -> None:
    # An empty environment: reaching the engine would fail with exit 3.
    code, out, err = run(tmp_path, str(CORPUS / name), *extra, environ={})
    assert (code, out) == (INPUT_ERROR, "")
    assert message in err


def test_a_missing_file_and_a_missing_engine_have_their_own_exit_codes(tmp_path: Path) -> None:
    code, _, err = run(tmp_path, str(tmp_path / "nowhere.sgf"))
    assert code == INPUT_ERROR and "cannot read" in err
    game = tmp_path / "game.sgf"
    game.write_bytes(SGF)
    code, _, err = run(tmp_path, str(game), environ={})
    assert code == ENGINE_ERROR and "engine_not_configured" in err


@pytest.mark.parametrize(
    ("moves", "message"),
    [
        ("B[ba];W[pd];B[ab];W[aa]", "error [suicide]: move 4 breaks the rules"),
        ("", "error [no_moves]"),
    ],
)
def test_rule_violations_and_empty_games_stop_before_the_engine(
    tmp_path: Path, moves: str, message: str
) -> None:
    # Real KataGo refuses a suicide; it must be an input error, not exit 3.
    game = tmp_path / "game.sgf"
    game.write_text(f"(;FF[4]GM[1]SZ[19]RU[Chinese]KM[7.5]{';' + moves if moves else ''})")
    code, out, err = run(tmp_path, str(game), environ={})
    assert (code, out) == (INPUT_ERROR, "")
    assert message in err and "use --" not in err
