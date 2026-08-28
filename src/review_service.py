from __future__ import annotations

from pathlib import Path

from src.analyzer import analyze_game_state
from src.game import validate_game, validate_review_options
from src.katago_client import EngineClient
from src.mistake_severity import DEFAULT_LOSS_THRESHOLD, DEFAULT_SEVERE_THRESHOLD, MAX_REVIEW_MISTAKES
from src.report_writer import generate_review_report
from src.review_result import ReviewResult, build_review_result
from src.sgf_parser import ParsedGame, parse_sgf, parse_sgf_file


def build_review_outputs_for_game(
    game: ParsedGame, engine: EngineClient,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD, limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> tuple[str, ReviewResult]:
    validate_game(game)
    validate_review_options(loss_threshold, limit, severe_threshold)
    review = build_review_result(game, analyze_game_state(game, engine), loss_threshold, severe_threshold, limit)
    return generate_review_report(review), review


def build_review_outputs_for_sgf(
    sgf_path: str | Path, engine: EngineClient,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD, limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> tuple[str, ReviewResult]:
    return build_review_outputs_for_game(parse_sgf_file(sgf_path), engine, loss_threshold, limit, severe_threshold)


def build_review_report_for_sgf(
    sgf_path: str | Path, engine: EngineClient,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD, limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> str:
    return build_review_outputs_for_sgf(sgf_path, engine, loss_threshold, limit, severe_threshold)[0]


def build_structured_review_for_sgf(
    sgf_path: str | Path, engine: EngineClient,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD, limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> ReviewResult:
    return build_review_outputs_for_sgf(sgf_path, engine, loss_threshold, limit, severe_threshold)[1]


def build_structured_review_for_game(
    game: ParsedGame, engine: EngineClient,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD, limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> ReviewResult:
    return build_review_outputs_for_game(game, engine, loss_threshold, limit, severe_threshold)[1]


def build_structured_review_for_sgf_text(
    sgf_text: str, engine: EngineClient,
    loss_threshold: float = DEFAULT_LOSS_THRESHOLD, limit: int = MAX_REVIEW_MISTAKES,
    severe_threshold: float = DEFAULT_SEVERE_THRESHOLD,
) -> ReviewResult:
    return build_structured_review_for_game(parse_sgf(sgf_text), engine, loss_threshold, limit, severe_threshold)
