"""Opt-in real-engine measurement. Raw evidence only for an explicitly selected public sample."""
import argparse
import copy
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import resource
import time
from unittest.mock import patch

from src.analyzer import analyze_game_state
from src.katago_client import KataGoClient
from src.katago_process import JsonlProcess
from src.sgf_parser import parse_sgf_file


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sgf")
    parser.add_argument("--visits", type=int, default=32)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--record-public-fixture", action="store_true")
    args = parser.parse_args()
    records, pids = [], []

    class RecordingProcess(JsonlProcess):
        def __init__(self, command):
            super().__init__(command)
            pids.append(self.pid)

        def exchange(self, requests, expected, timeout):
            result, warnings = super().exchange(requests, expected, timeout)
            if args.record_public_fixture:
                responses = copy.deepcopy(list(result.values()))
                for response in responses:
                    for model in response.get("models", []):
                        if "name" in model:
                            model["name"] = Path(model["name"]).name
                records.append({"requests": requests, "responses": responses, "warnings": warnings})
            return result, warnings

    game = parse_sgf_file(args.sgf)
    started = time.monotonic()
    with patch("src.katago_client.JsonlProcess", RecordingProcess):
        result = analyze_game_state(game, KataGoClient.from_environment(max_visits=args.visits))
    elapsed = time.monotonic() - started
    evidence = asdict(result.current_position.evidence)
    metadata = {key: evidence[key] for key in (
        "engine_version", "model_id", "model_sha256", "config_sha256", "max_visits", "rules", "komi",
    )}
    peak = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    peak_bytes = peak if platform.system() == "Darwin" else peak * 1024
    summary = {
        "platform": platform.platform(), "machine": platform.machine(),
        "python": platform.python_version(), "moves": len(game.moves),
        "sgf_sha256": hashlib.sha256(Path(args.sgf).read_bytes()).hexdigest(),
        "wall_seconds": elapsed, "engine_peak_rss_bytes": peak_bytes,
        "engine_process_count": len(pids), "positions": len(result.move_results) + 1,
        "forced_evaluations": sum(r.engine_analysis.evidence.played_source == "forced_root" for r in result.move_results),
        "metadata": metadata,
    }
    if args.record_public_fixture:
        summary["records"] = records
        summary["normalized"] = asdict(result)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=True, indent=2, allow_nan=False) + "\n")
    print(json.dumps({key: value for key, value in summary.items() if key not in {"records", "normalized"}}, indent=2))


if __name__ == "__main__":
    main()
