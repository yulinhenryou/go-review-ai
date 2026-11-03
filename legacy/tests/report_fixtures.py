"""Explicit synthetic evidence for exact M3 policy tests, not a production engine."""
from dataclasses import replace

from src.engine_types import AnalysisEvidence, CandidateMove, PositionAnalysis, PVMove
from src.sgf_parser import parse_sgf


def game_with_moves(count):
    points = ["aa", "cc", "ee", "gg", "ii", "kk", "mm", "oo", "qq", "ac"]
    return parse_sgf("(;SZ[19]RU[Chinese]KM[7.5]" + "".join(
        f";{'B' if i % 2 == 0 else 'W'}[{points[i]}]" for i in range(count)) + ")")


class FixedEvidenceEngine:
    def __init__(self, losses, overrides=None):
        self.losses = losses
        self.overrides = overrides or {}

    def analyze_position(self, position):
        turn = len(position.moves)
        current = position.analysis_kind == "current_position"
        loss = None if current else self.losses[turn]
        score = None if loss is None and not current else 2.0
        played_score = None if score is None or current else score - loss
        sign = 1 if position.to_play == "B" else -1
        winrate, played_winrate = 0.6, None if current else 0.4
        best = CandidateMove("pd", score, winrate, (PVMove(position.to_play, "pd"),), 64,
                             None if score is None else score * sign, winrate if sign == 1 else 1 - winrate)
        played = None if current else CandidateMove(position.played_move or "pass", played_score, played_winrate,
                                                    (), 64, None if played_score is None else played_score * sign,
                                                    played_winrate if sign == 1 else 1 - played_winrate)
        evidence = AnalysisEvidence("fixture", "a" * 64, "synthetic-policy-fixture", position.rules,
                                    position.komi, 64, f"fixture-{turn}", turn, 64, 0.01,
                                    "not_applicable" if current else "same_search", None, "b" * 64)
        value = PositionAnalysis(
            "pd", position.played_move, None if loss is None else max(0, loss), score, winrate,
            played_score, played_winrate, (best,), "B aa -> W bb (untrusted legacy text)",
            raw_score_loss=loss, played_candidate=played, evidence=evidence,
        )
        return replace(value, **self.overrides.get(turn, {}))
