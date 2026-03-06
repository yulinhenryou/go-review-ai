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
    "direction_error": "This likely chose the wrong side or direction of play.",
    "local_overplay": "This likely pushed too hard in a local fight.",
    "defensive_overreaction": "This looks playable, but likely more cautious than needed.",
    "endgame_loss": "This likely missed available endgame points.",
    "tactical_blunder": "This likely missed a concrete tactical detail.",
    "unclear": "Engine signals are mixed, so this pattern is not yet clear.",
}

_CATEGORY_TRAINING: dict[MistakeCategory, str] = {
    "direction_error": "Review opening direction principles and compare side choices.",
    "local_overplay": "Practice choosing calmer local continuations in fighting positions.",
    "defensive_overreaction": "Review examples where active play is stronger than pure safety.",
    "endgame_loss": "Do short endgame counting drills before each game session.",
    "tactical_blunder": "Do a focused life-and-death and reading exercise set.",
    "unclear": "Recheck this position manually because the pattern is not conclusive.",
}


def generate_review_report(game: ParsedGame, mistakes: list[ClassifiedMistake]) -> str:
    sections = [
        _game_summary(game, mistakes),
        _top_mistakes(game.board_size, mistakes),
        _mistake_explanations(game.board_size, mistakes),
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
        f"- Board: {game.board_size}x{game.board_size}",
        f"- Komi: {komi}",
        f"- Players: {black} (B) vs {white} (W)",
        f"- Result: {result}",
        f"- Moves analyzed: {len(game.moves)}",
        f"- Mistakes reviewed: {len(mistakes)}",
    ]
    return "\n".join(lines)


def _top_mistakes(board_size: int, mistakes: list[ClassifiedMistake]) -> str:
    lines = ["Top Mistakes"]
    if not mistakes:
        lines.append("- No mistakes matched the current selection threshold.")
        return "\n".join(lines)

    for idx, mistake in enumerate(mistakes, start=1):
        lines.append(
            f"{idx}. Move {mistake.move_number}: "
            f"played {_format_move(mistake.played_move, board_size)}, "
            f"best {_format_move(mistake.recommended_move, board_size)}, "
            f"loss {mistake.estimated_loss:.2f}, "
            f"{_CATEGORY_LABELS[mistake.category]}"
        )
    return "\n".join(lines)


def _mistake_explanations(board_size: int, mistakes: list[ClassifiedMistake]) -> str:
    lines = ["Mistake Explanations"]
    if not mistakes:
        lines.append("No mistake explanations are available.")
        return "\n".join(lines)

    for idx, mistake in enumerate(mistakes, start=1):
        lines.extend(_explanation_block(idx, board_size, mistake))
    return "\n".join(lines)


def _explanation_block(
    index: int, board_size: int, mistake: ClassifiedMistake
) -> list[str]:
    transition = _transition_phrase(index)
    played = _format_move(mistake.played_move, board_size)
    recommended = _format_move(mistake.recommended_move, board_size)
    label = _CATEGORY_LABELS[mistake.category]
    interpretation = _CATEGORY_INTERPRETATION[mistake.category]

    return [
        f"- Move {mistake.move_number} ({label})",
        (
            f"  {transition}, you played {played}; "
            f"KataGo prefers {recommended} (loss {mistake.estimated_loss:.2f})."
        ),
        f"  Why this matters: {interpretation}",
    ]


def _transition_phrase(index: int) -> str:
    options = (
        "In this position",
        "At this moment",
        "From an engine perspective",
    )
    return options[(index - 1) % len(options)]


def _training_suggestions(mistakes: list[ClassifiedMistake]) -> str:
    lines = ["Final Training Suggestions"]
    if not mistakes:
        lines.append("- Keep playing and collect more reviewed games.")
        return "\n".join(lines)

    counts = Counter(item.category for item in mistakes)
    lines.append("- Primary focus from this game:")
    for category, _count in counts.most_common(2):
        lines.append(f"- {_CATEGORY_LABELS[category]}: {_CATEGORY_TRAINING[category]}")

    lines.append("- In your next review, compare your move with the best move before reading comments.")
    return "\n".join(lines)


def _format_move(move: str | None, board_size: int) -> str:
    if move is None:
        return "pass"

    coord = _sgf_to_human_coord(move, board_size)
    if coord is None:
        return move
    return f"{move} ({coord})"


def _sgf_to_human_coord(move: str, board_size: int) -> str | None:
    if len(move) != 2 or board_size <= 0:
        return None

    x = ord(move[0]) - ord("a")
    y = ord(move[1]) - ord("a")
    if x < 0 or y < 0 or x >= board_size or y >= board_size:
        return None

    column = _go_column_label(x)
    row = board_size - y
    return f"{column}{row}"


def _go_column_label(index: int) -> str:
    # SGF uses a-based indexing. Human Go coordinates usually skip I.
    label_index = index
    if index >= 8:
        label_index += 1
    return chr(ord("A") + label_index)
