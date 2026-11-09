"""A game record as a review takes it: one SGF game, with rules and komi
confirmed before anything reaches the engine (MIGRATION G04, G05).

Parsing, extraction and replay are the rules core's. This module only
decides what a review accepts: exactly one game in the file, a rule set and
komi that are either confirmed by the caller or read unambiguously from the
record, and never a default filled in for a missing value (ADR-010).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Final, Literal

import weiqi_core

from weiqi.engine import AnalysisRequest

type RecordStatus = Literal["result_recorded", "unfinished_or_unknown"]

RULE_NAMES: Final = ("chinese", "japanese", "korean", "aga", "new-zealand", "tromp-taylor")
"""Rule-set names a review accepts; the rules core and KataGo know all of them."""


class ReviewInputError(ValueError):
    """A game that cannot be reviewed as given, with a stable `code`."""

    def __init__(
        self, code: str, message: str, field: str | None = None, move_number: int | None = None
    ) -> None:
        super().__init__(message)
        self.code = code
        self.field = field
        self.move_number = move_number


@dataclass(frozen=True, slots=True)
class GameInput:
    """One parsed game and what was noticed while reading it."""

    sgf: bytes
    sgf_sha256: str
    encoding: str
    record: weiqi_core.GameRecord
    input_warnings: tuple[str, ...]
    """Codes from parsing and extraction, sorted and without duplicates."""

    @property
    def record_status(self) -> RecordStatus:
        """A recorded result is metadata, not proof that every move was recorded."""
        result = self.record.info.result_text
        return (
            "result_recorded"
            if result and result.strip() not in ("", "?")
            else ("unfinished_or_unknown")
        )


def read_game(data: bytes) -> GameInput:
    """Parses SGF bytes holding exactly one game."""
    try:
        collection = weiqi_core.parse_sgf(data)
        if len(collection.games) != 1:
            raise ReviewInputError(
                "multiple_games" if collection.games else "no_game",
                "the SGF file must hold exactly one game",
            )
        record = weiqi_core.extract(collection.games[0])
    except weiqi_core.CoreError as error:
        raise ReviewInputError(error.code, str(error)) from error
    warnings = {w.code for w in collection.warnings} | {w.code for w in record.warnings}
    return GameInput(
        sgf=data,
        sgf_sha256=hashlib.sha256(data).hexdigest(),
        encoding=collection.encoding,
        record=record,
        input_warnings=tuple(sorted(warnings)),
    )


def recorded_rules(record: weiqi_core.GameRecord) -> str | None:
    """The record's `RU` as an accepted rule-set name, or `None` if it is
    missing or not one the review recognises."""
    text = (record.rules_text or "").strip().lower().replace(" ", "-").replace("_", "-")
    name = _ALIASES.get(text, text)
    return name if record.rules is not None and name in RULE_NAMES else None


_ALIASES: Final = {"nz": "new-zealand", "newzealand": "new-zealand", "tromptaylor": "tromp-taylor"}


def confirm(
    game: GameInput, rules: str | None = None, komi: float | None = None
) -> tuple[str, float]:
    """The rule-set name and komi for the review: the caller's values, else
    the record's. Anything still missing raises `metadata_unconfirmed`."""
    rules = rules if rules is not None else recorded_rules(game.record)
    komi = komi if komi is not None else game.record.komi
    missing = [name for name, value in (("rules", rules), ("komi", komi)) if value is None]
    if missing:
        raise ReviewInputError(
            "metadata_unconfirmed",
            f"confirm {' and '.join(missing)} before the review",
            field=missing[0],
        )
    assert rules is not None and komi is not None
    if rules not in RULE_NAMES:
        raise ReviewInputError("invalid_rules", f"rules must be one of {RULE_NAMES}", "rules")
    return rules, komi


REPEATED_POSITION: Final = "repeated_position"
"""The one replay warning that breaks no rule: a legal move recreated an
earlier arrangement of stones (possible where the rules have no superko)."""


def replay_warnings(game: GameInput, rules: str, komi: float) -> tuple[tuple[int, str], ...]:
    """What replaying the record under `rules` reported, as (move number,
    code) pairs: rule violations (`ko_violation`, `superko_violation`,
    `suicide`, `out_of_turn`) and `repeated_position`."""
    replay = game.record.replay(weiqi_core.Rules.from_name(rules), komi)
    return tuple((w.move_number, w.code) for w in replay.warnings)


def check_reviewable(game: GameInput, rules: str, komi: float) -> None:
    """Refuses records a review cannot evaluate honestly (ADR-P19): a game
    without moves, and a record whose move breaks the selected rules. The
    positions after an illegal move cannot arise in a legal game, so losses
    measured around it are not evidence; KataGo also refuses some of them
    (suicide). The error names the first offending move."""
    if not game.record.moves:
        raise ReviewInputError("no_moves", "the game has no moves to review", "moves")
    for number, code in replay_warnings(game, rules, komi):
        if code != REPEATED_POSITION:
            raise ReviewInputError(
                code, f"move {number} breaks the rules ({code})", "moves", move_number=number
            )


def review_request(
    game: GameInput, rules: str, komi: float, *, max_visits: int, pv_length: int = 8
) -> AnalysisRequest:
    """The whole-game analysis a review starts with: every turn, with ownership.
    The request replays the record in the rules core, which rejects
    impossible moves and invalid komi with their codes; `check_reviewable`
    then refuses empty games and rule violations."""
    record = game.record
    moves = tuple(record.moves)
    setup = record.setup
    request = AnalysisRequest(
        width=record.width,
        height=record.height,
        rules=rules,
        komi=komi,
        moves=moves,
        analyze_turns=tuple(range(len(moves) + 1)),
        max_visits=max_visits,
        pv_length=pv_length,
        include_ownership=True,
        initial_black=tuple(setup.black),
        initial_white=tuple(setup.white),
        initial_player=setup.to_play,
    )
    check_reviewable(game, rules, komi)
    return request
