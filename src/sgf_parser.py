from __future__ import annotations

import codecs
from pathlib import Path

from sgfmill import sgf, sgf_grammar

from src.game import (
    MAX_SGF_BYTES, MAX_SGF_NODES, GameInputError, GameMove, GameRecord,
    normalize_rules, validate_game, validate_komi,
)

# Keep historical imports working while consumers migrate to the shared model.
ParsedMove = GameMove
ParsedGame = GameRecord


def parse_sgf_file(
    path: str | Path, *, rules: str | None = None, komi: float | None = None,
) -> GameRecord:
    with Path(path).open("rb") as source:
        data = source.read(MAX_SGF_BYTES + 1)
    return parse_sgf_bytes(data, rules=rules, komi=komi)


def parse_sgf(
    text: str, *, rules: str | None = None, komi: float | None = None,
) -> GameRecord:
    try:
        data = text.encode("utf-8")
    except UnicodeError as exc:
        raise GameInputError("invalid_encoding", "SGF file must be UTF-8 text") from exc
    return parse_sgf_bytes(data, rules=rules, komi=komi)


def parse_sgf_bytes(
    data: bytes, *, rules: str | None = None, komi: float | None = None,
) -> GameRecord:
    if len(data) > MAX_SGF_BYTES:
        raise GameInputError("input_too_large", "SGF files must not exceed 1 MiB", field="file")
    try:
        data = data.decode("utf-8-sig").strip().encode("utf-8")
    except UnicodeError as exc:
        raise GameInputError("invalid_encoding", "SGF file must be UTF-8 text", field="file") from exc
    fallback_rules = normalize_rules(rules)
    validate_komi(komi)
    if not data.startswith(b"(") or not data[1:].lstrip().startswith(b";"):
        raise GameInputError("invalid_sgf", "Expected '(' at the start of SGF data", field="file")

    try:
        # sgfmill intentionally tolerates surrounding junk. The API does not.
        tokens, end = sgf_grammar.tokenise(data)
        if not tokens or tokens[:2] != [("D", b"("), ("D", b";")]:
            raise ValueError("expected an SGF game tree")
        if data[end:].strip():
            raise ValueError("trailing content or multiple-game collections are not supported")
        if sum(token == ("D", b";") for token in tokens) > MAX_SGF_NODES:
            raise GameInputError("input_too_large", "SGF must not exceed 5000 nodes", field="file")
        tree = sgf_grammar.parse_sgf_game(data)
        _check_properties(tree)
        root_data = tree.sequence[0]
        if "SZ" not in root_data:
            raise ValueError("Missing required SGF board size property: SZ")
        if root_data["SZ"] != [b"19"]:
            raise GameInputError("unsupported_board_size", "Only SZ[19] is supported", field="board_size")
        if "CA" in root_data and codecs.lookup(root_data["CA"][0].decode("ascii")).name != "utf-8":
            raise GameInputError("invalid_encoding", "Only CA[UTF-8] is supported", field="file")
        parsed = sgf.Sgf_game.from_coarse_game_tree(tree, override_encoding="utf-8")
        root = parsed.get_root()
        moves = []
        for node in parsed.main_sequence_iter():
            color, point = node.get_move()
            if color is not None:
                coordinate = None if point is None else chr(point[1] + 97) + chr(18 - point[0] + 97)
                moves.append(GameMove(color.upper(), coordinate))
        raw_rules = root.get("RU") if root.has_property("RU") else None
        game_rules = normalize_rules(raw_rules) if raw_rules is not None else fallback_rules
        game_komi = root.get("KM") if root.has_property("KM") else komi
        warnings = []
        pending = [tree]
        while pending:
            branch = pending.pop()
            if len(branch.children) > 1:
                warnings.append("first_variation_only")
                break
            pending.extend(branch.children)
        game = GameRecord(
            board_size=19, komi=game_komi, rules=game_rules,
            black_player=root.get("PB") if root.has_property("PB") else None,
            white_player=root.get("PW") if root.has_property("PW") else None,
            result=root.get("RE") if root.has_property("RE") else None,
            moves=tuple(moves), warnings=tuple(warnings),
        )
    except GameInputError:
        raise
    except (ValueError, LookupError, UnicodeError) as exc:
        raise GameInputError("invalid_sgf", f"Invalid SGF: {exc}", field="file") from exc
    validate_game(game, require_metadata=False)
    return game


def _check_properties(tree: sgf_grammar.Coarse_game_tree) -> None:
    root = tree.sequence[0]
    stack = [tree]
    singleton = {"B", "W", "SZ", "KM", "RU", "CA", "FF", "GM", "HA", "PB", "PW", "RE"}
    root_only = singleton - {"B", "W"}
    while stack:
        branch = stack.pop()
        stack.extend(branch.children)
        for node in branch.sequence:
            for prop, values in node.items():
                if not sgf_grammar.is_valid_property_identifier(prop):
                    raise ValueError("invalid property identifier")
                if prop in {"AB", "AW", "AE", "PL", "KO"}:
                    raise GameInputError("unsupported_property", f"SGF property {prop} is not supported in v1", field=prop)
                if prop in singleton and len(values) != 1:
                    raise ValueError(f"duplicate or multi-valued property: {prop}")
                if node is not root and prop in root_only:
                    raise GameInputError("unsupported_property", f"{prop} is only supported on the root node", field=prop)
                if prop == "HA" and values != [b"0"]:
                    raise GameInputError("unsupported_handicap", "Handicap games are not supported", field="HA")
                if prop == "GM" and values != [b"1"]:
                    raise GameInputError("unsupported_game", "Only Go (GM[1]) is supported", field="GM")
                if prop == "FF" and values != [b"4"]:
                    raise GameInputError("unsupported_format", "Only SGF FF[4] is supported", field="FF")
                if prop in {"B", "W"}:
                    raw = values[0]
                    # Reject sgfmill's legacy 'tt' pass alias: v1 uses empty values.
                    if raw and (len(raw) != 2 or any(c < 97 or c > 115 for c in raw)):
                        raise GameInputError("invalid_coordinate", "SGF moves must be two letters a-s or empty for pass", field=prop)
            if "B" in node and "W" in node:
                raise ValueError("a node cannot contain both B and W moves")
