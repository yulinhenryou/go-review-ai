"""Exports the prototype's behaviour for the M4 comparison suite (ROADMAP M4).

Run from `legacy/` with the prototype's own environment:

    .venv/bin/python -m scripts.export_review review ../testdata/sgf/sample-game.sgf \
        --visits 200 --output /tmp/legacy-sample-1.json
    .venv/bin/python -m scripts.export_review decide cases.json --output decisions.json

`review` runs one real-engine review (needs KATAGO_MODEL_PATH and
KATAGO_CONFIG_PATH) and writes a reduced document: provenance, per-move
losses and flags, and the mistake selections. `decide` reads a list of
`{"name", "file" | "text", "rules", "komi"}` cases and writes whether the
prototype accepts each one for review, with its error code. The new code
reads these documents; it never imports the prototype.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from src.game import GameInputError, validate_game
from src.katago_client import KataGoClient
from src.review_service import build_structured_review_for_game
from src.sgf_parser import parse_sgf_bytes

SCHEMA = "comparison.legacy.v1"
LOSS_THRESHOLD, SEVERE_THRESHOLD, LIMIT = 3.0, 5.0, 5


def review(args: argparse.Namespace) -> dict:
    data = args.sgf.read_bytes()
    game = parse_sgf_bytes(data, rules=args.rules, komi=args.komi)
    started = time.monotonic()
    result = build_structured_review_for_game(
        game,
        KataGoClient.from_environment(max_visits=args.visits),
        LOSS_THRESHOLD,
        LIMIT,
        SEVERE_THRESHOLD,
    ).to_dict()
    elapsed = time.monotonic() - started
    evidence = result["timeline"][0]["evidence"]
    return {
        "schema": SCHEMA,
        "sgf": args.sgf.name,
        "sgf_sha256": hashlib.sha256(data).hexdigest(),
        "rules": game.rules,
        "komi": game.komi,
        "engine": {
            key: evidence[key]
            for key in ("engine_version", "model_id", "model_sha256", "config_sha256", "max_visits")
        },
        "method": {"loss_threshold": LOSS_THRESHOLD, "severe_threshold": SEVERE_THRESHOLD, "limit": LIMIT},
        "wall_seconds": round(elapsed, 1),
        "status": result["status"],
        "input_warnings": list(result["game_summary"]["input_warnings"]),
        "warnings": list(result["warnings"]),
        "moves": [
            {
                "move_number": item["move_number"],
                "color": item["color"],
                "played": item["played_move"]["sgf"],
                "recommended": (item["recommended_move"] or {}).get("sgf"),
                "score_loss": item["score_loss"],
                "raw_score_loss": item["raw_score_loss"],
                "winrate_delta_pp": item["winrate_delta_pp"],
                "severity": item["severity"],
                "played_source": item["evidence"]["played_source"],
                "warnings": list(item["warnings"]),
            }
            for item in result["timeline"]
        ],
        "selected_mistakes": [item["move_number"] for item in result["selected_mistakes"]],
        "mistakes_above_threshold": [
            item["move_number"] for item in result["review"]["mistakes_above_threshold"]
        ],
    }


def decide(args: argparse.Namespace) -> list[dict]:
    decisions = []
    for case in json.loads(args.cases.read_text(encoding="utf-8")):
        if "file" in case:
            data = (args.cases.parent / case["file"]).read_bytes()
        else:
            data = case["text"].encode("utf-8")
        try:
            game = parse_sgf_bytes(data, rules=case.get("rules"), komi=case.get("komi"))
            validate_game(game)  # metadata required, as before a review
            decisions.append({"name": case["name"], "accepted": True, "code": None})
        except GameInputError as error:
            decisions.append({"name": case["name"], "accepted": False, "code": error.code})
    return decisions


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("review")
    one.add_argument("sgf", type=Path)
    one.add_argument("--visits", type=int, default=200)
    one.add_argument("--rules")
    one.add_argument("--komi", type=float)
    one.add_argument("--output", type=Path, required=True)
    many = commands.add_parser("decide")
    many.add_argument("cases", type=Path)
    many.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    document = review(args) if args.command == "review" else decide(args)
    args.output.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
