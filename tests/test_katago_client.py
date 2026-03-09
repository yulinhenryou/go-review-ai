import subprocess

import pytest

from src.katago_client import (
    KataGoClient,
    KataGoUnavailableError,
    MockEngineClient,
    PositionInput,
)


def test_mock_client_returns_structured_analysis() -> None:
    client = MockEngineClient()

    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="B",
        moves=(("B", "pd"), ("W", "dd"), ("B", "qp")),
        played_move="dc",
    )

    analysis = client.analyze_position(position)

    assert analysis.best_move == "qd"
    assert analysis.played_move == "dc"
    assert analysis.estimated_loss >= 0.0
    assert analysis.score_estimate == analysis.top_candidates[0].score_estimate
    assert analysis.winrate == analysis.top_candidates[0].winrate
    assert len(analysis.top_candidates) == 3
    assert analysis.top_candidates[0].move == "qd"
    assert "B" in analysis.pv_summary


def test_mock_client_accepts_best_move_as_zero_loss() -> None:
    client = MockEngineClient()

    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="W",
        moves=(("B", "pd"),),
        played_move="dq",
    )

    analysis = client.analyze_position(position)

    assert analysis.best_move == "dq"
    assert analysis.estimated_loss == 0.0
    assert analysis.played_score_estimate == analysis.score_estimate
    assert analysis.played_winrate == analysis.winrate


def test_mock_client_rejects_invalid_to_play() -> None:
    client = MockEngineClient()

    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play="X",  # type: ignore[arg-type]
        moves=(),
        played_move=None,
    )

    try:
        client.analyze_position(position)
    except ValueError as exc:
        assert "to_play" in str(exc)
    else:
        raise AssertionError("Expected ValueError for invalid to_play")


def test_mock_client_analyzes_position_like_input() -> None:
    client = MockEngineClient()

    analysis = client.analyze_position(
        PositionInput(
            board_size=13,
            komi=0.5,
            to_play="B",
            moves=(("B", "dd"), ("W", "jj")),
            played_move="kk",
        )
    )

    assert isinstance(analysis.best_move, str)
    assert len(analysis.top_candidates) == 3
    assert analysis.pv_summary
    assert analysis.estimated_loss > 0.0


def test_katago_client_parses_analysis_output(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KataGoClient(
        model_path="/tmp/model.bin.gz",
        config_path="/tmp/analysis.cfg",
        candidate_count=3,
        max_visits=64,
    )

    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args
        assert "go-review-ai" in kwargs["input"]
        return subprocess.CompletedProcess(
            args=["katago"],
            returncode=0,
            stdout=(
                '{"id":"go-review-ai","moveInfos":['
                '{"move":"Q16","scoreLead":2.4,"winrate":0.58,"pv":["Q16","D4","Q4"]},'
                '{"move":"D4","scoreLead":1.7,"winrate":0.55},'
                '{"move":"Q4","scoreLead":1.3,"winrate":0.53},'
                '{"move":"R16","scoreLead":0.9,"winrate":0.52}'
                "]}\n"
            ),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    analysis = client.analyze_position(
        PositionInput(
            board_size=19,
            komi=6.5,
            to_play="B",
            moves=(("B", "pd"), ("W", "dd")),
            played_move="dp",
        )
    )

    assert analysis.best_move == "pd"
    assert analysis.played_move == "dp"
    assert analysis.estimated_loss == 0.7
    assert analysis.score_estimate == 2.4
    assert analysis.winrate == 0.58
    assert analysis.played_score_estimate == 1.7
    assert analysis.played_winrate == 0.55
    assert [candidate.move for candidate in analysis.top_candidates] == ["pd", "dp", "pp"]
    assert analysis.pv_summary == "B pd -> W dp -> B pp"


def test_katago_client_reports_missing_binary(monkeypatch: pytest.MonkeyPatch) -> None:
    client = KataGoClient(
        model_path="/tmp/model.bin.gz",
        config_path="/tmp/analysis.cfg",
    )

    def _missing_binary(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        raise FileNotFoundError("No such file or directory: katago")

    monkeypatch.setattr(subprocess, "run", _missing_binary)

    with pytest.raises(KataGoUnavailableError) as exc_info:
        client.analyze_position(
            PositionInput(
                board_size=19,
                komi=6.5,
                to_play="B",
                moves=(),
                played_move="pd",
            )
        )

    assert "binary not found" in str(exc_info.value)


def test_katago_client_surfaces_payload_when_moveinfos_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = KataGoClient(
        model_path="/tmp/model.bin.gz",
        config_path="/tmp/analysis.cfg",
    )

    def _fake_run(*args, **kwargs):  # type: ignore[no-untyped-def]
        del args, kwargs
        return subprocess.CompletedProcess(
            args=["katago"],
            returncode=0,
            stdout='{"id":"go-review-ai","error":"invalid komi","field":"komi"}\n',
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", _fake_run)

    with pytest.raises(RuntimeError) as exc_info:
        client.analyze_position(
            PositionInput(
                board_size=19,
                komi=375.0,
                to_play="B",
                moves=(),
                played_move="pd",
            )
        )

    message = str(exc_info.value)
    assert "missing moveInfos" in message
    assert "invalid komi" in message
    assert "field=komi" in message
    assert "raw_payload" in message


def test_katago_client_from_environment_requires_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("KATAGO_MODEL_PATH", raising=False)
    monkeypatch.delenv("KATAGO_CONFIG_PATH", raising=False)

    with pytest.raises(KataGoUnavailableError):
        KataGoClient.from_environment()
