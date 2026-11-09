"""The review command line (MIGRATION R08), a development entry point:

    uv run python -m weiqi.review game.sgf --database sqlite:///weiqi.db

It reads one SGF file, takes rules and komi from the record unless given,
analyses every turn through the cached analyzer, stores the run and prints
the report (`--format text`, in `--locale`) or the result JSON. The engine
comes from `KATAGO_MODEL_PATH`, `KATAGO_CONFIG_PATH` and `KATAGO_PATH`; there
is no fallback engine and no default rules or komi.

Exit status: 0 on success, 2 when the input cannot be reviewed as given,
3 when the engine is unavailable or misbehaves.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, TextIO

from weiqi.engine import (
    CachedAnalyzer,
    EngineError,
    EngineSettings,
    InvalidRequestError,
    KataGoEngine,
)
from weiqi.explain import LOCALES, render_report
from weiqi.review.game_input import (
    RULE_NAMES,
    GameInput,
    ReviewInputError,
    confirm,
    read_game,
    review_request,
)
from weiqi.review.pipeline import Review, review_game
from weiqi.review.result import ReviewSettings
from weiqi.storage.database import connect
from weiqi.storage.migrate import upgrade
from weiqi.storage.results import SqlResultStore
from weiqi.storage.reviews import SqlReviewStore

if TYPE_CHECKING:
    from weiqi.engine import TurnResult

INPUT_ERROR = 2
ENGINE_ERROR = 3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m weiqi.review", description="Review one SGF game with KataGo."
    )
    parser.add_argument("sgf", type=Path, help="the SGF file (exactly one game)")
    parser.add_argument(
        "--database",
        required=True,
        help="SQLAlchemy URL of the cache and review store, e.g. sqlite:///weiqi.db; "
        "migrated to the latest schema before use",
    )
    parser.add_argument("--rules", choices=RULE_NAMES, help="confirm or override the record's RU")
    parser.add_argument("--komi", type=float, help="confirm or override the record's KM")
    parser.add_argument("--visits", type=int, default=200, help="maxVisits per turn (default 200)")
    parser.add_argument("--limit", type=int, help="list at most this many mistakes")
    parser.add_argument("--locale", choices=LOCALES, default="zh-CN")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--output", type=Path, help="write here instead of standard output")
    return parser


def _progress(total: int, stream: TextIO) -> Callable[[TurnResult], None]:
    """Counts analysed turns on a terminal; prints nothing when redirected."""
    done = 0

    def on_turn(_result: TurnResult) -> None:
        nonlocal done
        done += 1
        if stream.isatty():
            stream.write(f"\r{done}/{total}")
            if done == total:
                stream.write("\n")
            stream.flush()

    return on_turn


async def _review(
    game: GameInput,
    rules: str,
    komi: float,
    settings: ReviewSettings,
    database_url: str,
    environ: Mapping[str, str],
    stderr: TextIO,
) -> tuple[Review, str]:
    database = connect(database_url)
    try:
        upgrade(database)
        async with KataGoEngine(EngineSettings.from_environment(environ)) as engine:
            analyzer = CachedAnalyzer(engine, SqlResultStore(database))
            on_turn = _progress(len(game.record.moves) + 1, stderr)
            review = await review_game(analyzer, game, rules, komi, settings, on_turn=on_turn)
        run_id = await SqlReviewStore(database).save(
            game, review.result, review.analysis.identity, settings
        )
        return review, run_id
    finally:
        database.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    environ: Mapping[str, str] = os.environ,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
) -> int:
    args = _parser().parse_args(argv)
    try:
        game = read_game(args.sgf.read_bytes())
        rules, komi = confirm(game, args.rules, args.komi)
        settings = ReviewSettings(max_visits=args.visits, mistake_limit=args.limit)
        # Replays the record in the rules core now, so an impossible move or
        # invalid komi is reported before the engine starts.
        review_request(game, rules, komi, max_visits=settings.max_visits)
        review, run_id = asyncio.run(
            _review(game, rules, komi, settings, args.database, environ, stderr)
        )
    except OSError as error:
        stderr.write(f"error: cannot read {args.sgf}: {error.strerror}\n")
        return INPUT_ERROR
    except ReviewInputError as error:
        hint = f" (use --{error.field})" if error.field else ""
        stderr.write(f"error [{error.code}]: {error}{hint}\n")
        return INPUT_ERROR
    except InvalidRequestError as error:
        stderr.write(f"error [{error.code}]: {error}\n")
        return INPUT_ERROR
    except EngineError as error:
        stderr.write(f"engine error [{error.code}]: {error}\n")
        return ENGINE_ERROR

    result = review.result
    text = result.to_json() if args.format == "json" else render_report(result, args.locale)
    if args.output is None:
        stdout.write(text + "\n")
    else:
        args.output.write_text(text + "\n", encoding="utf-8")
    stderr.write(
        f"run {run_id}: {result.status}; {review.engine_turns} turns from the engine, "
        f"{review.cached_turns} from the cache\n"
    )
    return 0
