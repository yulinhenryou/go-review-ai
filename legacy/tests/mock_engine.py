from src.engine_types import CandidateMove, Move, Color, PositionAnalysis, PositionInput
from src.engine_protocol import validate_position as _validate_position


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
        candidate_move = (played_move or "pass") if position.analysis_kind == "played_move" else None
        played_candidate = _played_candidate_from_candidates(top_candidates, candidate_move)
        estimated_loss = round(
            max(0.0, top_candidates[0].score_estimate - played_candidate.score_estimate),
            2,
        )

        pv_summary = _pv_summary(position.to_play, top_candidates)

        return PositionAnalysis(
            best_move=best_move,
            played_move=played_move,
            estimated_loss=estimated_loss,
            score_estimate=top_candidates[0].score_estimate,
            winrate=top_candidates[0].winrate,
            played_score_estimate=played_candidate.score_estimate,
            played_winrate=played_candidate.winrate,
            top_candidates=top_candidates,
            pv_summary=pv_summary,
        )



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


def _played_candidate_from_candidates(
    candidates: tuple[CandidateMove, ...], played_move: Move | None
) -> CandidateMove:
    if not played_move:
        return candidates[0]

    for candidate in candidates:
        if candidate.move == played_move:
            return candidate

    # If the played move is outside top candidates, assume at least a bit worse
    # than the worst candidate we return.
    fallback = candidates[-1]
    return CandidateMove(
        move=played_move,
        score_estimate=round(fallback.score_estimate - 0.3, 2),
        winrate=max(0.0, round(fallback.winrate - 0.02, 2)),
    )


def _pv_summary(to_play: Color, candidates: tuple[CandidateMove, ...]) -> str:
    best = candidates[0].move
    reply = candidates[1].move if len(candidates) > 1 else "pass"
    follow_up = candidates[2].move if len(candidates) > 2 else "pass"
    if to_play == "B":
        return f"B {best} -> W {reply} -> B {follow_up}"
    return f"W {best} -> B {reply} -> W {follow_up}"
