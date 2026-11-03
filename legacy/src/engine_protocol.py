from __future__ import annotations

import math

from src.engine_types import CandidateMove, EngineProtocolError, PVMove, PositionInput
from src.game import validate_komi


def sgf_to_gtp(move: str | None, board_size: int) -> str:
    if move is None or move == "pass":
        return "pass"
    if not isinstance(move, str) or len(move) != 2:
        raise ValueError("Invalid SGF coordinate")
    x, y = ord(move[0]) - 97, ord(move[1]) - 97
    if not (0 <= x < board_size and 0 <= y < board_size):
        raise ValueError("SGF coordinate out of range")
    return f"{chr(65 + x + (x >= 8))}{board_size - y}"


def gtp_to_sgf(move: object, board_size: int) -> str:
    if not isinstance(move, str):
        raise EngineProtocolError("Invalid engine coordinate")
    move = move.strip().upper()
    if move == "PASS":
        return "pass"
    columns = "ABCDEFGHJKLMNOPQRSTUVWXYZ"[:board_size]
    if len(move) < 2 or move[0] not in columns or not move[1:].isascii() or not move[1:].isdigit():
        raise EngineProtocolError("Invalid engine coordinate")
    row = int(move[1:])
    if not 1 <= row <= board_size:
        raise EngineProtocolError("Engine coordinate out of range")
    return chr(97 + columns.index(move[0])) + chr(97 + board_size - row)


def validate_position(position: PositionInput) -> None:
    if type(position.board_size) is not int or not 1 <= position.board_size <= 19:
        raise ValueError("board_size must be between 1 and 19")
    if position.to_play not in {"B", "W"}:
        raise ValueError("to_play must be B or W")
    if position.rules not in {"japanese", "chinese"}:
        raise ValueError("Unsupported rules")
    validate_komi(position.komi)
    if position.komi is None:
        raise ValueError("Explicit komi is required")
    if position.analysis_kind not in {"played_move", "current_position"}:
        raise ValueError("Unsupported analysis_kind")
    if position.analysis_kind == "current_position" and position.played_move is not None:
        raise ValueError("Current-position requests cannot contain a played move")
    sgf_to_gtp(position.played_move, position.board_size)
    for color, move in position.moves:
        if color not in {"B", "W"}:
            raise ValueError("Invalid history color")
        sgf_to_gtp(move, position.board_size)


def optional_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise EngineProtocolError(f"Invalid numeric field: {field}")
    try:
        if not math.isfinite(value):
            raise EngineProtocolError(f"Invalid numeric field: {field}")
    except OverflowError as exc:
        raise EngineProtocolError(f"Invalid numeric field: {field}") from exc
    if field == "winrate" and not 0 <= value <= 1:
        raise EngineProtocolError("Winrate outside [0,1]")
    return float(value)


def optional_visits(value: object) -> int | None:
    if value is not None and (type(value) is not int or value < 0):
        raise EngineProtocolError("Invalid visits")
    return value


def candidate(info: dict, position: PositionInput) -> CandidateMove:
    move = gtp_to_sgf(info.get("move"), position.board_size)
    score = optional_number(info.get("scoreLead"), "scoreLead")
    winrate = optional_number(info.get("winrate"), "winrate")
    pv_raw = info.get("pv")
    if pv_raw is not None and not isinstance(pv_raw, list):
        raise EngineProtocolError("PV must be a list")
    pv = tuple(PVMove(
        position.to_play if i % 2 == 0 else ("W" if position.to_play == "B" else "B"),
        gtp_to_sgf(item, position.board_size),
    ) for i, item in enumerate(pv_raw or []))
    if pv and pv[0].move != move:
        raise EngineProtocolError("PV does not belong to its candidate")
    return CandidateMove(
        move=move,
        score_estimate=score if score is None or position.to_play == "B" else -score,
        winrate=winrate if winrate is None or position.to_play == "B" else 1 - winrate,
        pv=pv, visits=optional_visits(info.get("visits")),
        score_black=score, winrate_black=winrate,
    )


def candidates(payload: dict, position: PositionInput) -> tuple[CandidateMove, ...]:
    root = payload.get("rootInfo")
    if not isinstance(root, dict) or root.get("currentPlayer") != position.to_play:
        raise EngineProtocolError("Root player does not match requested position")
    infos = payload.get("moveInfos")
    if not isinstance(infos, list) or any(not isinstance(i, dict) for i in infos):
        raise EngineProtocolError("Missing or invalid moveInfos")
    orders = [i.get("order") for i in infos]
    if (any(type(order) is not int or order < 0 for order in orders)
            or len(set(orders)) != len(orders) or (orders and min(orders) != 0)):
        raise EngineProtocolError("Invalid candidate order")
    result = tuple(candidate(i, position) for i in sorted(infos, key=lambda i: i["order"]))
    if len({c.move for c in result}) != len(result):
        raise EngineProtocolError("Duplicate candidate move")
    return result
