import copy
from dataclasses import asdict
import json
from pathlib import Path

from src.analyzer import analyze_game_state
from src.katago_client import KataGoClient
from src.sgf_parser import parse_sgf_file


def test_recorded_real_responses_reproduce_normalized_evidence():
    data = json.loads(Path("tests/fixtures/katago_real_short.json").read_text())
    records = iter(data["records"][1:])

    class ReplaySession:
        def exchange(self, requests, expected, timeout):
            record = next(records)
            assert len(requests) == len(record["requests"])
            ids = {}
            for actual, saved in zip(requests, record["requests"], strict=True):
                ids[saved["id"]] = actual["id"]
                assert {k: v for k, v in actual.items() if k != "id"} == {k: v for k, v in saved.items() if k != "id"}
            response = {(ids[item["id"]], item["turnNumber"]): item | {"id": ids[item["id"]]}
                        for item in record["responses"]}
            assert set(response) == expected
            return response, tuple(record["warnings"])

    metadata = data["metadata"]
    engine = KataGoClient(model_path="unused", config_path="unused", max_visits=metadata["max_visits"])
    engine._session = ReplaySession()
    engine._version, engine._model_id = metadata["engine_version"], metadata["model_id"]
    engine._model_hash, engine._config_hash = metadata["model_sha256"], metadata["config_sha256"]
    actual = json.loads(json.dumps(asdict(analyze_game_state(parse_sgf_file("samples/sample_game.sgf"), engine))))
    expected = copy.deepcopy(data["normalized"])
    for game in (actual, expected):
        values = [move["engine_analysis"] for move in game["move_results"]] + [game["current_position"]]
        for value in values:
            for key in ("request_id", "played_request_id", "elapsed_seconds"):
                value["evidence"].pop(key)
    assert actual == expected
    assert next(records, None) is None


def test_recorded_fixture_has_no_local_absolute_paths():
    text = Path("tests/fixtures/katago_real_short.json").read_text()
    for prefix in ("/Users/", "/opt/", "/private/", "/tmp/"):
        assert prefix not in text
