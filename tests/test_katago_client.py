import copy

import pytest

from src.analyzer import analyze_game_state
from src.engine_factory import build_default_engine
from src.engine_protocol import candidate, candidates, gtp_to_sgf
from src.engine_types import EngineProtocolError, KataGoUnavailableError, PositionInput
from src.katago_client import KataGoClient
from src.sgf_parser import parse_sgf_file
from tests.mock_engine import MockEngineClient


def position(**kwargs):
    defaults = dict(board_size=19, komi=6.5, to_play="B", moves=(), played_move="dp")
    return PositionInput(**(defaults | kwargs))


def payload(query, turn):
    color = query["initialPlayer"] if turn % 2 == 0 else (
        "W" if query["initialPlayer"] == "B" else "B")
    sign = 1 if color == "B" else -1
    moves = query.get("allowMoves", [{}])[0].get("moves", ["Q16", "D4", "Q4"])
    return {"id": query["id"], "turnNumber": turn, "isDuringSearch": False,
            "rootInfo": {"currentPlayer": color, "visits": 64, "scoreLead": sign * 2.4, "winrate": .6},
            "moveInfos": [{"move": m, "order": i, "visits": 32,
                           "scoreLead": sign * (2.4 - i * .7), "winrate": .58 - i * .03,
                           "pv": [m]} for i, m in enumerate(moves)]}


class FakeSession:
    def __init__(self, command):
        self.command, self.calls, self.closed = command, [], False
        self.transform = lambda value, query: value

    def exchange(self, requests, expected, timeout):
        self.calls.append(copy.deepcopy(requests))
        results = {}
        for query in requests:
            if query.get("action") == "query_version":
                results[(query["id"], None)] = {"version": "1.16.4"}
            elif query.get("action") == "query_models":
                results[(query["id"], None)] = {"models": [{"internalName": "fixture-model"}]}
            else:
                for turn in reversed(query["analyzeTurns"]):
                    results[(query["id"], turn)] = self.transform(payload(query, turn), query)
        assert set(results) == expected
        return results, ()

    def close(self):
        self.closed = True


@pytest.fixture
def client(tmp_path, monkeypatch):
    model, config = tmp_path / "model.bin", tmp_path / "analysis.cfg"
    model.write_bytes(b"fixture model")
    config.write_text("fixture config")
    sessions = []
    def factory(command):
        session = FakeSession(command)
        sessions.append(session)
        return session
    monkeypatch.setattr("src.katago_client.JsonlProcess", factory)
    monkeypatch.setattr("src.katago_client.shutil.which", lambda _: "/fake/katago")
    return KataGoClient(model_path=model, config_path=config, max_visits=64), sessions


@pytest.mark.parametrize("color", ["B", "W"])
def test_candidate_score_perspective_and_real_pv(client, color):
    engine, sessions = client
    value = engine.analyze_position(position(to_play=color))
    assert value.estimated_loss == pytest.approx(.7)
    assert value.score_estimate == 2.4
    assert value.score_black == (2.4 if color == "B" else -2.4)
    assert value.winrate == pytest.approx(.58 if color == "B" else .42)
    assert value.pv_summary == color + " pd"
    assert len(value.top_candidates[0].pv) == 1
    assert sessions[0].closed
    assert "reportAnalysisWinratesAs=BLACK" in sessions[0].command[-1]
    assert len(value.evidence.model_sha256) == 64
    assert value.evidence.raw_perspective == "BLACK"


def test_one_loaded_process_batches_whole_game(client):
    engine, sessions = client
    value = analyze_game_state(parse_sgf_file("samples/sample_game.sgf"), engine)
    assert len(sessions) == 1
    query = sessions[0].calls[1][0]
    assert query["analyzeTurns"] == [0, 1, 2, 3, 4]
    assert [r.engine_analysis.evidence.turn_number for r in value.move_results] == [0, 1, 2, 3]
    assert value.current_position.evidence.turn_number == 4
    assert value.current_position.estimated_loss is None
    assert sessions[0].closed


@pytest.mark.parametrize("actual", ["aa", None])
def test_missing_actual_move_or_pass_gets_explicit_search(client, actual):
    engine, sessions = client
    value = engine.analyze_position(position(played_move=actual, rules="chinese", komi=0))
    forced = sessions[0].calls[2][0]
    assert forced["allowMoves"] == [{"player": "B", "moves": ["pass" if actual is None else "A19"], "untilDepth": 1}]
    assert forced["rules"] == "chinese" and forced["komi"] == 0 and forced["maxVisits"] == 64
    assert value.evidence.played_source == "forced_root"
    assert value.played_candidate.move == (actual or "pass")
    assert value.evidence.played_request_id != value.evidence.request_id


def test_missing_actual_even_after_search_stays_missing(client):
    engine, sessions = client
    with engine:
        sessions[0].transform = lambda p, q: p | {"moveInfos": []} if "allowMoves" in q else p
        value = engine.analyze_position(position(played_move=None))
    assert value.estimated_loss is None and value.played_score_estimate is None
    assert "played_evaluation_unavailable" in value.evidence.warnings


def test_current_position_does_not_request_a_pass_evaluation(client):
    engine, sessions = client
    value = engine.analyze_position(position(played_move=None, analysis_kind="current_position"))
    assert len(sessions[0].calls) == 2
    assert value.played_candidate is None
    assert value.played_winrate is None


def test_empty_candidate_terminal_response_uses_only_root_value(client):
    engine, sessions = client
    with engine:
        sessions[0].transform = lambda p, q: p | {"moveInfos": []}
        value = engine.analyze_position(position(played_move=None, analysis_kind="current_position"))
    assert value.best_move is None
    assert value.top_candidates == () and value.pv_summary == ""
    assert value.score_estimate == 2.4
    assert "no_candidate_moves" in value.evidence.warnings


def test_missing_values_never_use_utility_or_fifty_percent():
    value = candidate({"move": "Q16", "utility": .9}, position())
    assert value.score_estimate is None and value.winrate is None
    assert value.pv == ()


@pytest.mark.parametrize("field,value", [
    ("scoreLead", float("nan")), ("scoreLead", float("inf")), ("scoreLead", True),
    ("scoreLead", "3"), ("winrate", 1.1), ("winrate", -.1), ("winrate", False),
    ("visits", -1), ("visits", True), ("pv", "Q16"), ("pv", ["bad"]),
    ("pv", ["D4"]), ("move", "Z19"), ("move", "I4"), ("move", "Q20"),
])
def test_invalid_candidate_fields_are_rejected(field, value):
    info = {"move": "Q16", "scoreLead": 2, "winrate": .5, "visits": 20, "pv": ["Q16"]}
    info[field] = value
    with pytest.raises(EngineProtocolError):
        candidate(info, position())


def test_order_not_array_order_selects_recommendation(client):
    engine, sessions = client
    with engine:
        sessions[0].transform = lambda p, q: p | {"moveInfos": list(reversed(p["moveInfos"]))}
        value = engine.analyze_position(position())
    assert value.best_move == "pd"


def test_negative_raw_difference_is_retained(client):
    engine, sessions = client
    with engine:
        def transform(p, q):
            p["moveInfos"][1]["scoreLead"] = 3.5
            return p
        sessions[0].transform = transform
        value = engine.analyze_position(position())
    assert value.estimated_loss == 0 and value.raw_score_loss == pytest.approx(-1.1)
    assert "negative_difference_search_noise" in value.evidence.warnings


def test_protocol_error_cleans_up_process(client):
    engine, sessions = client
    with pytest.raises(EngineProtocolError):
        with engine:
            sessions[0].transform = lambda p, q: p | {"rootInfo": {"currentPlayer": "X"}}
            engine.analyze_position(position())
    assert sessions[0].closed and engine._session is None


def test_readiness_and_no_local_paths_in_provenance(client):
    engine, sessions = client
    value = engine.readiness()
    assert value["status"] == "ready" and value["model_id"] == "fixture-model"
    assert "/" not in str(value)
    assert sessions[0].closed


def test_default_engine_never_falls_back(monkeypatch):
    monkeypatch.delenv("KATAGO_MODEL_PATH", raising=False)
    monkeypatch.delenv("KATAGO_CONFIG_PATH", raising=False)
    with pytest.raises(KataGoUnavailableError):
        build_default_engine()


def test_missing_binary(monkeypatch):
    monkeypatch.setattr("src.katago_client.shutil.which", lambda _: None)
    with pytest.raises(KataGoUnavailableError, match="binary not found"):
        KataGoClient(model_path="missing", config_path="missing").readiness()


def test_missing_model(client):
    engine, sessions = client
    engine._model_path = engine._model_path.parent / "missing"
    with pytest.raises(KataGoUnavailableError, match="missing or empty"):
        engine.readiness()
    assert not sessions


def test_duplicate_orders_or_wrong_player_rejected():
    query = {"id": "a", "initialPlayer": "B"}
    value = payload(query, 0)
    value["moveInfos"][1]["order"] = 0
    with pytest.raises(EngineProtocolError):
        candidates(value, position())
    value = payload(query, 0)
    with pytest.raises(EngineProtocolError):
        candidates(value, position(to_play="W"))
    value["moveInfos"] = value["moveInfos"][1:]
    with pytest.raises(EngineProtocolError):
        candidates(value, position())
    with pytest.raises(EngineProtocolError):
        candidate({"move": "D4", "scoreLead": 10**1000}, position())


@pytest.mark.parametrize("gtp,sgf", [("A19", "aa"), ("T1", "ss"), ("Q16", "pd"), ("pass", "pass")])
def test_coordinate_mapping(gtp, sgf):
    assert gtp_to_sgf(gtp, 19) == sgf


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
