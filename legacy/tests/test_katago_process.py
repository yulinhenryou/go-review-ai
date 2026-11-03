import os
from pathlib import Path
import sys

import pytest

from src.engine_types import EngineProtocolError, KataGoUnavailableError
from src.katago_process import JsonlProcess
from src.analysis_control import AnalysisControl, AnalysisCancelled


def session(mode):
    return JsonlProcess([sys.executable, "-u", str(Path("tests/fixtures/jsonl_engine.py").resolve()), mode])


@pytest.mark.parametrize("mode", ["normal", "interim", "fragmented", "stderr", "warning"])
def test_jsonl_matching_out_of_order_and_reused_session(mode):
    engine = session(mode)
    pid = engine.pid
    try:
        result, warnings = engine.exchange(
            [{"id": "first", "analyzeTurns": [0, 1]}, {"id": "second", "analyzeTurns": [2]}],
            {("first", 0), ("first", 1), ("second", 2)}, 3,
        )
        assert len(result) == 3
        assert warnings == (("engine_warning",) if mode == "warning" else ())
        result, _ = engine.exchange([{"id": "next", "analyzeTurns": [3]}], {("next", 3)}, 3)
        assert result[("next", 3)]["isDuringSearch"] is False
    finally:
        engine.close()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


@pytest.mark.parametrize("mode,error", [
    ("timeout", KataGoUnavailableError), ("exit", KataGoUnavailableError),
    ("malformed", EngineProtocolError), ("nonfinite", EngineProtocolError),
    ("wrong_id", EngineProtocolError), ("wrong_turn", EngineProtocolError),
    ("bool_turn", EngineProtocolError), ("no_final_flag", EngineProtocolError),
    ("duplicate", EngineProtocolError), ("error", EngineProtocolError),
    ("rules_warning", EngineProtocolError), ("oversized", EngineProtocolError),
])
def test_failures_close_process_without_exposing_engine_text(mode, error):
    engine = session(mode)
    pid = engine.pid
    with pytest.raises(error) as info:
        engine.exchange([{"id": "test", "analyzeTurns": [0, 1]}], {("test", 0), ("test", 1)}, .3 if mode == "timeout" else 3)
    assert "/path" not in str(info.value)
    engine.close()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_cancellation_reaps_the_running_subprocess():
    import threading
    engine = session("timeout")
    pid = engine.pid
    engine.control = AnalysisControl()
    timer = threading.Timer(.05, engine.control.cancelled.set)
    timer.start()
    try:
        with pytest.raises(AnalysisCancelled):
            engine.exchange([{"id": "cancel", "analyzeTurns": [0]}], {("cancel", 0)}, 30)
    finally:
        timer.join()
        engine.close()
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
