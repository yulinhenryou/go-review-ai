"""Single-game review: runs the engine searches a review needs and assembles
the result from them. It sits above the engine and metrics layers and is the
only part of the review that talks to the engine."""

from weiqi.review.game_input import (
    RULE_NAMES,
    GameInput,
    ReviewInputError,
    confirm,
    read_game,
    recorded_rules,
    review_request,
)
from weiqi.review.pipeline import Review, review_game
from weiqi.review.played import search_played_moves
from weiqi.review.result import RESULT_SCHEMA, ReviewResult, ReviewSettings, build_result

__all__ = [
    "RESULT_SCHEMA",
    "RULE_NAMES",
    "GameInput",
    "Review",
    "ReviewInputError",
    "ReviewResult",
    "ReviewSettings",
    "build_result",
    "confirm",
    "read_game",
    "recorded_rules",
    "review_game",
    "review_request",
    "search_played_moves",
]
