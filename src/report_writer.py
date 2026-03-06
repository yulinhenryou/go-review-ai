from __future__ import annotations

from collections import Counter

from src.classifier import ClassifiedMistake, MistakeCategory
from src.sgf_parser import ParsedGame

_CATEGORY_LABELS: dict[MistakeCategory, str] = {
    "direction_error": "Direction error",
    "local_overplay": "Local overplay",
    "defensive_overreaction": "Defensive overreaction",
    "endgame_loss": "Endgame value loss",
    "tactical_blunder": "Tactical blunder",
    "unclear": "Unclear classification",
}

_CATEGORY_INTERPRETATION: dict[MistakeCategory, str] = {
    "direction_error": "The move likely chose the wrong side or direction of play.",
    "local_overplay": "The move appears too forceful in a local area.",
    "defensive_overreaction": "The move is playable but likely too cautious.",
    "endgame_loss": "The move likely missed endgame point value.",
    "tactical_blunder": "The move likely misses a concrete tactical detail.",
    "unclear": "The classification is unclear from the available engine signals.",
}

_CATEGORY_TRAINING: dict[MistakeCategory, str] = {
    "direction_error": "Review opening direction principles and compare side choices.",
    "local_overplay": "Practice choosing calmer local continuations in fight positions.",
    "defensive_overreaction": "Review examples where active play is stronger than safe play.",
    "endgame_loss": "Do short endgame counting drills before each game session.",
    "tactical_blunder": "Do a focused life-and-death and reading exercise set.",
    "unclear": "Recheck this position manually because the pattern is not conclusive.",
}


def generate_review_report(game: ParsedGame, mistakes: list[ClassifiedMistake]) -> str:
    sections = [
        _game_summary(game, mistakes),
        _top_mistakes(mistakes),
        _mistake_explanations(mistakes),
        _training_suggestions(mistakes),
    ]
    return "\n\n".join(sections)


def _game_summary(game: ParsedGame, mistakes: list[ClassifiedMistake]) -> str:
    komi = f"{game.komi:.1f}" if game.komi is not None else "unknown"
    black = game.black_player or "Unknown Black"
    white = game.white_player or "Unknown White"
    result = game.result or "unknown"
    lines = [
        "Game Summary",
        f"- Board size: {game.board_size}x{game.board_size}",
        f"- Komi: {komi}",
        f"- Players: {black} (B) vs {white} (W)",
        f"- Result: {result}",
        f"- Moves analyzed: {len(game.moves)}",
        f"- Mistakes reviewed: {len(mistakes)}",
    ]
    return "\n".join(lines)


def _top_mistakes(mistakes: list[ClassifiedMistake]) -> str:
    lines = ["Top Mistakes"]
    if not mistakes:
        lines.append("- No mistakes matched the current selection threshold.")
        return "\n".join(lines)

    for idx, mistake in enumerate(mistakes, start=1):
        lines.append(
            f"{idx}. move={mistake.move_number} "
            f"played={_format_move(mistake.played_move)} "
            f"recommended={mistake.recommended_move} "
            f"loss={mistake.estimated_loss:.2f} "
            f"category={mistake.category}"
        )
    return "\n".join(lines)


def _mistake_explanations(mistakes: list[ClassifiedMistake]) -> str:
    lines = ["Mistake Explanations"]
    if not mistakes:
        lines.append("No mistake explanations are available.")
        return "\n".join(lines)

    for mistake in mistakes:
        facts = (
            f"Move {mistake.move_number}: "
            f"Engine facts: played {_format_move(mistake.played_move)}, "
            f"recommended {mistake.recommended_move}, "
            f"estimated loss {mistake.estimated_loss:.2f}. "
        )
        interpretation = (
            "Interpretation: "
            f"{_CATEGORY_LABELS[mistake.category]}. "
            f"{_CATEGORY_INTERPRETATION[mistake.category]}"
        )
        lines.append(facts + interpretation)
    return "\n".join(lines)


def _training_suggestions(mistakes: list[ClassifiedMistake]) -> str:
    lines = ["Final Training Suggestions"]
    if not mistakes:
        lines.append("- Keep playing and collect more reviewed games.")
        return "\n".join(lines)

    counts = Counter(item.category for item in mistakes)
    lines.append("- Primary focus based on this game:")
    for category, _count in counts.most_common(2):
        lines.append(f"- {_CATEGORY_LABELS[category]}: {_CATEGORY_TRAINING[category]}")

    lines.append(
        "- In your next review, compare your move against the engine move before reading comments."
    )
    return "\n".join(lines)


def _format_move(move: str | None) -> str:
    return move if move is not None else "pass"
