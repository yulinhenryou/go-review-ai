"""Single-game review: runs the engine searches a review needs and assembles
metrics from them. It sits above the engine and metrics layers and is the
only part of the review that talks to the engine."""

from weiqi.review.played import search_played_moves

__all__ = ["search_played_moves"]
