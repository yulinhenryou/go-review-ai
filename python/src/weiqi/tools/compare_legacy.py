"""The M4 comparison suite: the new review against the prototype (ROADMAP M4).

The prototype runs in its own environment and exports reduced documents
(`legacy/scripts/export_review.py`); this module never imports it. It reads
those documents and the new pipeline's `review.v1` results, reduced to the
same shape, and compares:

- **Losses:** the prototype's score loss is a same-root loss (best candidate
  minus the played move, ADR-P02), so it is compared with the new same-root
  diagnostic, per move, in clamped points.
- **Mistake sets:** moves at or above the prototype's 3-point line, and its
  top five by loss, selected the prototype's way from either run.
- **Noise first:** the prototype is run twice on each game; how much those
  two runs differ is the envelope. The tolerances are derived from it and
  recorded before any new run is compared (`tolerances` command).
- **Decisions:** which inputs each side accepts for review.
- **Warnings:** every prototype warning code maps to a new code.

    uv run python -m weiqi.tools.compare_legacy reduce-new result.json --output new.json
    uv run python -m weiqi.tools.compare_legacy envelope DIR
    uv run python -m weiqi.tools.compare_legacy decide cases.json --output new-decisions.json
    uv run python -m weiqi.tools.compare_legacy check DIR
"""

from __future__ import annotations

import argparse
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, cast

LEGACY_SCHEMA: Final = "comparison.legacy.v1"
NEW_SCHEMA: Final = "comparison.new.v1"
TOLERANCE_SCHEMA: Final = "comparison.tolerances.v1"
LOSS_THRESHOLD: Final = 3.0
"""The prototype's default mistake line (ADR-P17 keeps it for this comparison)."""
TOP_LIMIT: Final = 5

WARNING_EQUIVALENTS: Final[Mapping[str, tuple[str, ...]]] = {
    # Prototype code -> the new codes that report the same condition, in
    # `warnings`, `diagnostic_warnings` (same-root) or `game.input_warnings`.
    "negative_difference_search_noise": ("negative_difference_search_noise",),
    "low_visits": ("low_visits",),
    "separate_search": ("separate_search",),
    "played_evaluation_unavailable": ("played_move_not_searched",),
    "missing_score_evidence": ("missing_score_evidence",),
    "missing_winrate_evidence": ("missing_winrate_evidence",),
    "missing_current_value": ("missing_current_value",),
    "missing_pv": ("missing_pv",),
    "recommendation_unavailable": ("recommendation_unavailable",),
    "no_candidate_moves": ("no_candidate_moves",),
    # Missing root values of the recommendation or the played move.
    "missing_value": ("missing_score_evidence", "missing_winrate_evidence"),
    "missing_played_value": ("missing_score_evidence", "missing_winrate_evidence"),
    # A result always names the engine it was computed with, and test
    # doubles never reach the production path, so nothing is left to flag.
    "unverified_engine": (),
    "first_variation_only": ("first_variation_only",),
}
"""Every warning code the prototype emits (`src/katago_client.py`,
`src/mistake_selector.py`, `src/review_result.py`, `src/sgf_parser.py`)."""

NEW_ALSO_ACCEPTS: Final[Mapping[str, str]] = {
    # Cases the prototype refuses as unsupported and the new review accepts,
    # with the reason. Every other case must get the same decision.
    "kejie_gbk_without_ca": "the rules core reads non-UTF-8 files (encoding_guessed)",
    "declared_gb2312": "the rules core decodes declared GB2312",
    "junk_before_one_game": "the rules core skips text outside the game tree, with a warning",
    "unclosed_tree": "the rules core reads an unclosed tree, with a warning",
    "play_after_two_passes": "play after two passes breaks no rule; "
    "the prototype did not support it",
    "white_moves_first": "the first player comes from PL or the first move "
    "(rules core, M1), as in handicap records",
    "handicap_setup": "setup stones (AB/AW/PL) are supported",
    "board_9x9": "every board size from 2 to 19 is supported",
    "korean_rules": "Korean, AGA, New Zealand and Tromp-Taylor rules are supported",
}


# --- Reduced runs ---


@dataclass(frozen=True, slots=True)
class Run:
    """One review run of one game, as the comparison reads it."""

    source: str
    sgf_sha256: str
    engine: tuple[str, str, str, int]
    """Engine version, model SHA-256, config SHA-256, maxVisits."""
    moves: tuple[tuple[int, str, str | None], ...]
    """(move number, colour, SGF point or `None` for a pass)."""
    losses: Mapping[int, float | None]
    """Clamped same-root loss per move number."""


def load_run(document: Mapping[str, Any]) -> Run:
    if document["schema"] not in (LEGACY_SCHEMA, NEW_SCHEMA):
        raise ValueError(f"unknown comparison document {document['schema']!r}")
    engine = document["engine"]
    return Run(
        source="legacy" if document["schema"] == LEGACY_SCHEMA else "new",
        sgf_sha256=document["sgf_sha256"],
        engine=(
            engine["engine_version"],
            engine["model_sha256"],
            engine["config_sha256"],
            engine["max_visits"],
        ),
        moves=tuple((m["move_number"], m["color"], m["played"]) for m in document["moves"]),
        losses={m["move_number"]: m["score_loss"] for m in document["moves"]},
    )


def _sgf_point(move: object) -> str | None:
    if move == "pass":
        return None
    x, y = cast(tuple[int, int], move)
    return chr(97 + x) + chr(97 + y)


def reduce_new(result: Mapping[str, Any], sgf_name: str) -> dict[str, Any]:
    """A `review.v1` result in the shape of the prototype's export."""
    engine, game = result["engine"], result["game"]
    return {
        "schema": NEW_SCHEMA,
        "sgf": sgf_name,
        "sgf_sha256": game["sgf_sha256"],
        "rules": game["rules"],
        "komi": game["komi"],
        "engine": {
            "engine_version": engine["version"],
            "model_id": engine["model_name"],
            "model_sha256": engine["model_sha256"],
            "config_sha256": engine["config_sha256"],
            "max_visits": engine["max_visits"],
        },
        "status": result["status"],
        "warnings": result["warnings"],
        "diagnostic_warnings": result["diagnostic_warnings"],
        "moves": [
            {
                "move_number": m["move_number"],
                "color": m["color"],
                "played": _sgf_point(m["move"]),
                "recommended": None if m["best_move"] is None else _sgf_point(m["best_move"]),
                "score_loss": m["same_root_score_loss"],
                "raw_score_loss": m["same_root_raw_score_loss"],
                "sequential_score_loss": m["score_loss"],
                "flags": m["same_root_flags"],
            }
            for m in result["timeline"]
        ],
    }


# --- Statistics ---


def quantile(values: Sequence[float], q: float) -> float:
    """Nearest-rank quantile: the smallest value with at least `q` of the
    values at or below it. Deterministic, and always an observed value."""
    if not values:
        raise ValueError("no values")
    ordered = sorted(values)
    return ordered[max(0, math.ceil(q * len(ordered)) - 1)]


def above_threshold(run: Run, threshold: float = LOSS_THRESHOLD) -> frozenset[int]:
    return frozenset(n for n, loss in run.losses.items() if loss is not None and loss >= threshold)


def top_mistakes(
    run: Run, threshold: float = LOSS_THRESHOLD, limit: int = TOP_LIMIT
) -> tuple[int, ...]:
    """The prototype's selection: losses at or above the line, ranked by
    unrounded loss, then move number; never padded."""
    ranked = sorted(above_threshold(run, threshold), key=lambda n: (-(run.losses[n] or 0.0), n))
    return tuple(ranked[:limit])


def jaccard(a: Iterable[int], b: Iterable[int]) -> float:
    """Shared moves over all moves of either set; two empty sets agree completely."""
    left, right = set(a), set(b)
    union = left | right
    return 1.0 if not union else len(left & right) / len(union)


@dataclass(frozen=True, slots=True)
class PairStats:
    """How two runs of one game differ."""

    compared: int
    differences: tuple[float, ...]
    """|loss a - loss b| for every move both runs evaluated, in move order."""
    above_threshold_jaccard: float
    top_jaccard: float

    def share_within(self, tolerance: float) -> float:
        return sum(d <= tolerance for d in self.differences) / len(self.differences)


def compare_runs(a: Run, b: Run) -> PairStats:
    if a.moves != b.moves or a.sgf_sha256 != b.sgf_sha256:
        raise ValueError("the runs are not of the same game")
    if a.engine != b.engine:
        raise ValueError(f"the runs used different engines: {a.engine} and {b.engine}")
    differences = tuple(
        abs(la - lb)
        for n in sorted(a.losses)
        if (la := a.losses[n]) is not None and (lb := b.losses.get(n)) is not None
    )
    return PairStats(
        compared=len(differences),
        differences=differences,
        above_threshold_jaccard=jaccard(above_threshold(a), above_threshold(b)),
        top_jaccard=jaccard(top_mistakes(a), top_mistakes(b)),
    )


# --- Accept / reject decisions ---


def new_decisions(cases_path: Path) -> list[dict[str, Any]]:
    """Whether the new review accepts each case: one game, confirmed rules
    and komi, and a record the rules core can replay."""
    from weiqi.engine import InvalidRequestError
    from weiqi.review import ReviewInputError, confirm, read_game, replay_warnings, review_request

    decisions = []
    for case in json.loads(cases_path.read_text(encoding="utf-8")):
        if "file" in case:
            data = (cases_path.parent / case["file"]).read_bytes()
        else:
            data = case["text"].encode("utf-8")
        try:
            game = read_game(data)
            rules, komi = confirm(game, case.get("rules"), case.get("komi"))
            review_request(game, rules, komi, max_visits=1)
            warnings = [*game.input_warnings, *(c for _, c in replay_warnings(game, rules, komi))]
            decisions.append(
                {"name": case["name"], "accepted": True, "code": None, "warnings": warnings}
            )
        except (ReviewInputError, InvalidRequestError) as error:
            decisions.append(
                {"name": case["name"], "accepted": False, "code": error.code, "warnings": []}
            )
    return decisions


# --- The check ---


def check_decisions(
    legacy: Sequence[Mapping[str, Any]], new: Sequence[Mapping[str, Any]]
) -> list[str]:
    """Problems with the new decisions: a case the prototype accepts and the
    new review refuses, or a case only the new review accepts without a
    recorded reason."""
    by_name = {d["name"]: d for d in new}
    if set(by_name) != {d["name"] for d in legacy}:
        raise ValueError("the decisions cover different cases")
    problems = []
    for old in legacy:
        current = by_name[old["name"]]
        if old["accepted"] and not current["accepted"]:
            problems.append(f"{old['name']}: refused ({current['code']}), the prototype accepts it")
        if current["accepted"] and not old["accepted"] and old["name"] not in NEW_ALSO_ACCEPTS:
            problems.append(f"{old['name']}: accepted, the prototype refuses it ({old['code']})")
    return problems


def check_report(directory: Path) -> dict[str, Any]:
    """Every check of the suite on the documents in `directory`: the
    prototype's runs, the new runs (`new-<game>.json`), both sides'
    decisions and the tolerances recorded before the new runs."""
    tolerances = _read(directory / "tolerances.json")
    if tolerances["schema"] != TOLERANCE_SCHEMA:
        raise ValueError("unknown tolerance document")
    tolerance, min_share = tolerances["loss_tolerance_points"], tolerances["min_share_within"]
    slack, envelope = tolerances["set_slack"], tolerances["envelope"]["games"]
    problems: list[str] = []
    games: dict[str, Any] = {}
    pooled: dict[int, list[float]] = {1: [], 2: []}
    for game, legacy_runs in _legacy_pairs(directory).items():
        new = load_run(_read(directory / f"new-{game}.json"))
        rows = []
        for index, old in enumerate(legacy_runs, start=1):
            stats = compare_runs(new, old)
            pooled[index].extend(stats.differences)
            row = {"legacy_run": index, **_summary(stats)}
            row["share_within_tolerance"] = round(stats.share_within(tolerance), 3)
            rows.append(row)
            for key in ("above_threshold_jaccard", "top_jaccard"):
                floor = envelope[game][key] - slack
                if getattr(stats, key) < floor - 1e-9:
                    problems.append(
                        f"{game} vs legacy run {index}: {key} {row[key]} below {floor:.3f}"
                    )
        games[game] = {
            "new_above_threshold": sorted(above_threshold(new)),
            "new_top": list(top_mistakes(new)),
            "legacy_top": [list(top_mistakes(run)) for run in legacy_runs],
            "comparisons": rows,
        }
    shares = {}
    for index, differences in pooled.items():
        share = sum(d <= tolerance for d in differences) / len(differences)
        shares[f"legacy_run_{index}"] = {
            **_quantiles(differences),
            "share_within_tolerance": round(share, 4),
        }
        if share < min_share:
            problems.append(
                f"legacy run {index}: {share:.1%} of moves within {tolerance} points, "
                f"below {min_share:.0%}"
            )
    problems += check_decisions(
        _read(directory / "legacy-decisions.json"), _read(directory / "new-decisions.json")
    )
    return {
        "passed": not problems,
        "problems": problems,
        "tolerance_points": tolerance,
        "min_share_within": min_share,
        "pooled": shares,
        "games": games,
    }


# --- Command line ---


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, document: object) -> None:
    path.write_text(json.dumps(document, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def _legacy_pairs(directory: Path) -> dict[str, tuple[Run, Run]]:
    """`legacy-<game>-1.json` and `-2.json` for each game in `directory`."""
    pairs = {}
    for first in sorted(directory.glob("legacy-*-1.json")):
        game = first.name.removeprefix("legacy-").removesuffix("-1.json")
        second = first.with_name(f"legacy-{game}-2.json")
        pairs[game] = (load_run(_read(first)), load_run(_read(second)))
    return pairs


def envelope_report(directory: Path) -> dict[str, Any]:
    """The prototype's run-to-run spread per game and pooled over games."""
    games: dict[str, Any] = {}
    pooled: list[float] = []
    for game, (a, b) in _legacy_pairs(directory).items():
        stats = compare_runs(a, b)
        pooled.extend(stats.differences)
        games[game] = _summary(stats)
    return {"games": games, "pooled": _quantiles(pooled)}


def _quantiles(values: Sequence[float]) -> dict[str, float | int]:
    return {
        "moves": len(values),
        "p50": round(quantile(values, 0.5), 3),
        "p90": round(quantile(values, 0.9), 3),
        "p95": round(quantile(values, 0.95), 3),
        "max": round(max(values), 3),
    }


def _summary(stats: PairStats) -> dict[str, Any]:
    return {
        **_quantiles(stats.differences),
        "above_threshold_jaccard": round(stats.above_threshold_jaccard, 3),
        "top_jaccard": round(stats.top_jaccard, 3),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m weiqi.tools.compare_legacy")
    commands = parser.add_subparsers(dest="command", required=True)
    reduce = commands.add_parser("reduce-new", help="reduce a review.v1 result")
    reduce.add_argument("result", type=Path)
    reduce.add_argument("--sgf-name", required=True)
    reduce.add_argument("--output", type=Path, required=True)
    envelope = commands.add_parser("envelope", help="the prototype's run-to-run spread")
    envelope.add_argument("directory", type=Path)
    check = commands.add_parser("check", help="every check against the recorded tolerances")
    check.add_argument("directory", type=Path)
    decide = commands.add_parser("decide", help="the new pipeline's accept/reject decisions")
    decide.add_argument("cases", type=Path)
    decide.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "reduce-new":
        _write(args.output, reduce_new(_read(args.result), args.sgf_name))
    elif args.command == "envelope":
        print(json.dumps(envelope_report(args.directory), indent=1))
    elif args.command == "check":
        report = check_report(args.directory)
        print(json.dumps(report, ensure_ascii=False, indent=1))
        return 0 if report["passed"] else 1
    else:
        _write(args.output, new_decisions(args.cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
