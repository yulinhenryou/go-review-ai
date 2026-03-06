from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

Color = Literal["B", "W"]
Move = str


@dataclass(frozen=True)
class PositionInput:
    board_size: int
    komi: float | None
    to_play: Color
    moves: tuple[tuple[Color, Move | None], ...]
    played_move: Move | None


@dataclass(frozen=True)
class CandidateMove:
    move: Move
    score_estimate: float
    winrate: float


@dataclass(frozen=True)
class PositionAnalysis:
    best_move: Move
    played_move: Move | None
    estimated_loss: float
    top_candidates: tuple[CandidateMove, ...]
    pv_summary: str


class EngineClient(Protocol):
    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        """Analyze one Go position and return structured results."""


class KataGoUnavailableError(RuntimeError):
    """Raised when the KataGo binary/config/model cannot be used."""


class KataGoClient:
    """Subprocess-backed KataGo client using JSON analysis mode."""

    def __init__(
        self,
        *,
        model_path: str | Path,
        config_path: str | Path,
        katago_path: str = "katago",
        candidate_count: int = 3,
        max_visits: int = 200,
        timeout_seconds: float = 20.0,
    ) -> None:
        if candidate_count <= 0:
            raise ValueError("candidate_count must be positive")
        if max_visits <= 0:
            raise ValueError("max_visits must be positive")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self._katago_path = katago_path
        self._model_path = str(model_path)
        self._config_path = str(config_path)
        self._candidate_count = candidate_count
        self._max_visits = max_visits
        self._timeout_seconds = timeout_seconds

    @classmethod
    def from_environment(
        cls,
        *,
        katago_path: str = "katago",
        candidate_count: int = 3,
        max_visits: int = 200,
        timeout_seconds: float = 20.0,
    ) -> "KataGoClient":
        model_path = os.environ.get("KATAGO_MODEL_PATH")
        config_path = os.environ.get("KATAGO_CONFIG_PATH")
        if not model_path or not config_path:
            raise KataGoUnavailableError(
                "Set KATAGO_MODEL_PATH and KATAGO_CONFIG_PATH to use KataGo."
            )
        return cls(
            model_path=model_path,
            config_path=config_path,
            katago_path=katago_path,
            candidate_count=candidate_count,
            max_visits=max_visits,
            timeout_seconds=timeout_seconds,
        )

    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        _validate_position(position)
        query = self._build_query(position)
        payload = self._run_query(query)
        move_infos = payload.get("moveInfos")

        if not isinstance(move_infos, list) or not move_infos:
            raise RuntimeError(_missing_move_infos_error(payload))

        top_candidates = tuple(
            _to_candidate(move_info, position.board_size) for move_info in move_infos[: self._candidate_count]
        )
        if not top_candidates:
            raise RuntimeError("KataGo returned no candidate moves")

        best_move = top_candidates[0].move
        played_move = position.played_move
        estimated_loss = _estimate_loss_from_katago(
            move_infos=move_infos,
            played_move=played_move,
            best_score=top_candidates[0].score_estimate,
            board_size=position.board_size,
            fallback_candidates=top_candidates,
        )
        pv_summary = _pv_summary_from_katago(
            to_play=position.to_play,
            best_move_info=move_infos[0],
            board_size=position.board_size,
            fallback_candidates=top_candidates,
        )

        return PositionAnalysis(
            best_move=best_move,
            played_move=played_move,
            estimated_loss=estimated_loss,
            top_candidates=top_candidates,
            pv_summary=pv_summary,
        )

    def _build_query(self, position: PositionInput) -> dict[str, object]:
        moves: list[list[str]] = []
        for color, move in position.moves:
            moves.append([color, _sgf_to_gtp(move, position.board_size)])

        query: dict[str, object] = {
            "id": "go-review-ai",
            "boardXSize": position.board_size,
            "boardYSize": position.board_size,
            "rules": "japanese",
            "maxVisits": self._max_visits,
            "moves": moves,
            "initialPlayer": _initial_player_for_query(position.to_play, len(moves)),
        }
        if position.komi is not None:
            query["komi"] = float(position.komi)
        return query

    def _run_query(self, query: dict[str, object]) -> dict[str, object]:
        command = [
            self._katago_path,
            "analysis",
            "-model",
            self._model_path,
            "-config",
            self._config_path,
        ]

        try:
            completed = subprocess.run(
                command,
                input=json.dumps(query) + "\n",
                capture_output=True,
                text=True,
                check=False,
                timeout=self._timeout_seconds,
            )
        except FileNotFoundError as exc:
            raise KataGoUnavailableError(
                f"KataGo binary not found: {self._katago_path}"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise KataGoUnavailableError(
                f"KataGo analysis timed out after {self._timeout_seconds:.1f}s"
            ) from exc

        if completed.returncode != 0:
            stderr = (completed.stderr or "").strip()
            detail = stderr if stderr else f"exit code {completed.returncode}"
            raise KataGoUnavailableError(f"KataGo failed: {detail}")

        lines = [line for line in (completed.stdout or "").splitlines() if line.strip()]
        if not lines:
            raise RuntimeError("KataGo returned empty output")

        last_line = lines[-1]
        try:
            payload = json.loads(last_line)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Failed to parse KataGo JSON response") from exc
        if not isinstance(payload, dict):
            raise RuntimeError("KataGo response was not a JSON object")
        return payload


class MockEngineClient:
    """Deterministic mock for pipeline development before real KataGo wiring."""

    def __init__(self, candidate_count: int = 3) -> None:
        if candidate_count <= 0:
            raise ValueError("candidate_count must be positive")
        self._candidate_count = candidate_count

    def analyze_position(self, position: PositionInput) -> PositionAnalysis:
        _validate_position(position)

        top_candidates = _mock_candidates(position, self._candidate_count)
        best_move = top_candidates[0].move
        played_move = position.played_move
        estimated_loss = _estimate_loss(top_candidates, played_move)

        pv_summary = _pv_summary(position.to_play, top_candidates)

        return PositionAnalysis(
            best_move=best_move,
            played_move=played_move,
            estimated_loss=estimated_loss,
            top_candidates=top_candidates,
            pv_summary=pv_summary,
        )


def _validate_position(position: PositionInput) -> None:
    if position.board_size <= 0:
        raise ValueError("board_size must be positive")
    if position.to_play not in {"B", "W"}:
        raise ValueError("to_play must be 'B' or 'W'")


def _to_candidate(move_info: dict[str, object], board_size: int) -> CandidateMove:
    raw_move = move_info.get("move")
    if not isinstance(raw_move, str):
        raise RuntimeError("KataGo moveInfo missing move")

    score_raw = move_info.get("scoreLead")
    if not isinstance(score_raw, (int, float)):
        score_raw = move_info.get("utility")
    if not isinstance(score_raw, (int, float)):
        raise RuntimeError("KataGo moveInfo missing scoreLead/utility")

    winrate_raw = move_info.get("winrate")
    winrate = float(winrate_raw) if isinstance(winrate_raw, (int, float)) else 0.5

    return CandidateMove(
        move=_gtp_to_sgf(raw_move, board_size),
        score_estimate=float(score_raw),
        winrate=winrate,
    )


def _initial_player_for_query(to_play: Color, move_count: int) -> Color:
    if move_count % 2 == 0:
        return to_play
    return "W" if to_play == "B" else "B"


def _estimate_loss_from_katago(
    *,
    move_infos: list[object],
    played_move: Move | None,
    best_score: float,
    board_size: int,
    fallback_candidates: tuple[CandidateMove, ...],
) -> float:
    if played_move is None:
        return 0.0

    for move_info in move_infos:
        if not isinstance(move_info, dict):
            continue
        raw_move = move_info.get("move")
        score_raw = move_info.get("scoreLead")
        if not isinstance(score_raw, (int, float)):
            score_raw = move_info.get("utility")
        if not isinstance(raw_move, str) or not isinstance(score_raw, (int, float)):
            continue
        if _gtp_to_sgf(raw_move, board_size) == played_move:
            return round(max(0.0, best_score - float(score_raw)), 2)

    worst_score = fallback_candidates[-1].score_estimate
    return round(max(0.0, best_score - worst_score + 0.3), 2)


def _pv_summary_from_katago(
    *,
    to_play: Color,
    best_move_info: dict[str, object],
    board_size: int,
    fallback_candidates: tuple[CandidateMove, ...],
) -> str:
    pv_raw = best_move_info.get("pv")
    if isinstance(pv_raw, list):
        pv_moves = [
            _gtp_to_sgf(item, board_size)
            for item in pv_raw
            if isinstance(item, str)
        ]
        if pv_moves:
            return _pv_summary_from_moves(to_play, pv_moves[:3])
    return _pv_summary(
        to_play=to_play,
        candidates=fallback_candidates,
    )


def _pv_summary_from_moves(to_play: Color, moves: list[str]) -> str:
    colors = ["B", "W", "B"] if to_play == "B" else ["W", "B", "W"]
    padded = list(moves)
    while len(padded) < 3:
        padded.append("pass")
    return " -> ".join(
        f"{color} {move}" for color, move in zip(colors, padded[:3], strict=True)
    )


def _sgf_to_gtp(move: Move | None, board_size: int) -> str:
    if move is None:
        return "pass"
    if len(move) != 2:
        raise ValueError(f"Unsupported SGF move format: {move}")
    x = ord(move[0]) - ord("a")
    y_from_top = ord(move[1]) - ord("a")
    if not (0 <= x < board_size and 0 <= y_from_top < board_size):
        raise ValueError(f"Move out of board range: {move}")
    return f"{_x_to_gtp_column(x)}{board_size - y_from_top}"


def _gtp_to_sgf(move: str, board_size: int) -> str:
    lowered = move.strip().lower()
    if lowered == "pass":
        return "pass"
    if not lowered:
        return move.lower()

    split = 0
    while split < len(move) and move[split].isalpha():
        split += 1

    letters = move[:split].upper()
    digits = move[split:]
    if not letters or not digits.isdigit():
        return move.lower()

    x = _gtp_column_to_x(letters)
    y = int(digits)
    if x is None or y < 1 or y > board_size:
        return move.lower()

    y_from_top = board_size - y
    if y_from_top < 0 or y_from_top >= board_size:
        return move.lower()

    return f"{chr(ord('a') + x)}{chr(ord('a') + y_from_top)}"


def _x_to_gtp_column(x: int) -> str:
    column_code = ord("A") + x
    if column_code >= ord("I"):
        column_code += 1
    return chr(column_code)


def _gtp_column_to_x(column: str) -> int | None:
    if len(column) != 1:
        return None
    letter = column.upper()
    if not ("A" <= letter <= "Z") or letter == "I":
        return None
    x = ord(letter) - ord("A")
    if letter > "I":
        x -= 1
    return x


def _missing_move_infos_error(payload: dict[str, object]) -> str:
    error = payload.get("error")
    field = payload.get("field")
    request_id = payload.get("id")

    prefix = "KataGo response missing moveInfos"
    details: list[str] = []

    if isinstance(error, str) and error:
        details.append(f"error={error}")
    if isinstance(field, str) and field:
        details.append(f"field={field}")
    if isinstance(request_id, str) and request_id:
        details.append(f"id={request_id}")

    payload_preview = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    if len(payload_preview) > 600:
        payload_preview = payload_preview[:600] + "...(truncated)"

    if details:
        return f"{prefix} ({', '.join(details)}). raw_payload={payload_preview}"
    return f"{prefix}. raw_payload={payload_preview}"


def _mock_candidates(position: PositionInput, candidate_count: int) -> tuple[CandidateMove, ...]:
    opening_book = {
        "B": [
            CandidateMove(move="qd", score_estimate=1.8, winrate=0.54),
            CandidateMove(move="dp", score_estimate=1.2, winrate=0.52),
            CandidateMove(move="pq", score_estimate=0.7, winrate=0.50),
        ],
        "W": [
            CandidateMove(move="dq", score_estimate=-1.1, winrate=0.48),
            CandidateMove(move="cp", score_estimate=-1.6, winrate=0.47),
            CandidateMove(move="qq", score_estimate=-2.0, winrate=0.45),
        ],
    }

    if len(position.moves) < 2:
        return tuple(opening_book[position.to_play][:candidate_count])

    # Slightly vary mock output by move-count bucket for deterministic diversity.
    bucket = len(position.moves) % 3
    if bucket == 0:
        return tuple(opening_book[position.to_play][:candidate_count])
    if bucket == 1:
        return tuple(
            [
            CandidateMove(move="jj", score_estimate=0.9, winrate=0.53),
            CandidateMove(move="kj", score_estimate=0.3, winrate=0.50),
            CandidateMove(move="jk", score_estimate=-0.2, winrate=0.49),
            ][:candidate_count]
        )
    return tuple(
        [
            CandidateMove(move="cn", score_estimate=2.1, winrate=0.57),
            CandidateMove(move="co", score_estimate=1.3, winrate=0.54),
            CandidateMove(move="bn", score_estimate=0.6, winrate=0.51),
        ][:candidate_count]
    )


def _estimate_loss(candidates: tuple[CandidateMove, ...], played_move: Move | None) -> float:
    if not played_move:
        return 0.0

    best_score = candidates[0].score_estimate

    for candidate in candidates:
        if candidate.move == played_move:
            return round(max(0.0, best_score - candidate.score_estimate), 2)

    # If the played move is outside top candidates, assume at least a bit worse
    # than the worst candidate we return.
    worst_score = candidates[-1].score_estimate
    return round(max(0.0, best_score - worst_score + 0.3), 2)


def _pv_summary(to_play: Color, candidates: tuple[CandidateMove, ...]) -> str:
    best = candidates[0].move
    reply = candidates[1].move if len(candidates) > 1 else "pass"
    follow_up = candidates[2].move if len(candidates) > 2 else "pass"
    if to_play == "B":
        return f"B {best} -> W {reply} -> B {follow_up}"
    return f"W {best} -> B {reply} -> W {follow_up}"
