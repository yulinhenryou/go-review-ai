from src.analyzer import MoveAnalysisResult
from src.classifier import (
    classify_mistake,
    classify_selected_mistakes,
    extract_features,
    print_classification_summary,
)
from src.mistake_severity import severity_from_loss
from src.katago_client import CandidateMove, PositionAnalysis, PositionInput
from src.mistake_selector import SelectedMistake


def test_classify_mistake_direction_error() -> None:
    result = _make_result(
        move_number=20,
        played_move="pp",
        best_move="dd",
        estimated_loss=1.1,
        top_candidates=(
            CandidateMove("dd", score_estimate=2.0, winrate=0.56),
            CandidateMove("pp", score_estimate=1.3, winrate=0.52),
            CandidateMove("dq", score_estimate=0.9, winrate=0.50),
        ),
    )
    assert classify_mistake(extract_features(result)) == "direction_error"


def test_classify_mistake_local_overplay() -> None:
    result = _make_result(
        move_number=45,
        played_move="fg",
        best_move="ff",
        estimated_loss=1.4,
        top_candidates=(
            CandidateMove("ff", score_estimate=2.2, winrate=0.57),
            CandidateMove("ef", score_estimate=1.6, winrate=0.54),
            CandidateMove("fe", score_estimate=1.2, winrate=0.52),
        ),
    )
    assert classify_mistake(extract_features(result)) == "local_overplay"


def test_classify_mistake_defensive_overreaction() -> None:
    result = _make_result(
        move_number=52,
        played_move="fg",
        best_move="ff",
        estimated_loss=1.0,
        top_candidates=(
            CandidateMove("ff", score_estimate=1.9, winrate=0.55),
            CandidateMove("fg", score_estimate=1.5, winrate=0.53),
            CandidateMove("ef", score_estimate=0.8, winrate=0.50),
        ),
    )
    assert classify_mistake(extract_features(result)) == "defensive_overreaction"


def test_classify_mistake_endgame_loss() -> None:
    result = _make_result(
        move_number=150,
        played_move="aa",
        best_move="ab",
        estimated_loss=0.9,
        top_candidates=(
            CandidateMove("ab", score_estimate=0.8, winrate=0.51),
            CandidateMove("aa", score_estimate=0.1, winrate=0.49),
            CandidateMove("ba", score_estimate=-0.2, winrate=0.48),
        ),
    )
    assert classify_mistake(extract_features(result)) == "endgame_loss"


def test_classify_mistake_tactical_blunder() -> None:
    result = _make_result(
        move_number=76,
        played_move="nn",
        best_move="cc",
        estimated_loss=2.8,
        top_candidates=(
            CandidateMove("cc", score_estimate=3.1, winrate=0.61),
            CandidateMove("cd", score_estimate=2.0, winrate=0.57),
            CandidateMove("dc", score_estimate=1.5, winrate=0.55),
        ),
    )
    assert classify_mistake(extract_features(result)) == "tactical_blunder"


def test_classify_mistake_unclear() -> None:
    result = _make_result(
        move_number=68,
        played_move="jj",
        best_move="jk",
        estimated_loss=0.4,
        top_candidates=(
            CandidateMove("jk", score_estimate=0.6, winrate=0.51),
            CandidateMove("kj", score_estimate=0.5, winrate=0.50),
            CandidateMove("jj", score_estimate=0.4, winrate=0.50),
        ),
    )
    assert classify_mistake(extract_features(result)) == "unclear"


def test_classify_selected_mistakes_and_print_summary(capsys) -> None:
    results = [
        _make_result(
            move_number=20,
            played_move="pp",
            best_move="dd",
            estimated_loss=1.1,
            top_candidates=(
                CandidateMove("dd", score_estimate=2.0, winrate=0.56),
                CandidateMove("pp", score_estimate=1.3, winrate=0.52),
                CandidateMove("dq", score_estimate=0.9, winrate=0.50),
            ),
        ),
        _make_result(
            move_number=76,
            played_move="nn",
            best_move="cc",
            estimated_loss=2.8,
            top_candidates=(
                CandidateMove("cc", score_estimate=3.1, winrate=0.61),
                CandidateMove("cd", score_estimate=2.0, winrate=0.57),
                CandidateMove("dc", score_estimate=1.5, winrate=0.55),
            ),
        ),
    ]
    selected = [
        SelectedMistake(
            move_number=20,
            played_move="pp",
            recommended_move="dd",
            estimated_loss=1.1,
        ),
        SelectedMistake(
            move_number=76,
            played_move="nn",
            recommended_move="cc",
            estimated_loss=2.8,
        ),
    ]

    classified = classify_selected_mistakes(selected, results)

    assert [item.category for item in classified] == [
        "direction_error",
        "tactical_blunder",
    ]
    assert [item.severity for item in classified] == [
        "inaccuracy",
        "mistake",
    ]
    assert [item.winrate_delta for item in classified] == [-0.04, -0.08]

    print_classification_summary(classified)
    out = capsys.readouterr().out
    assert "Move 20: played=pp recommended=dd loss=1.10 category=direction_error severity=inaccuracy" in out
    assert "Move 76: played=nn recommended=cc loss=2.80 category=tactical_blunder severity=mistake" in out
    assert "Category totals: direction_error=1, tactical_blunder=1" in out


def test_severity_from_loss_uses_threshold_bands() -> None:
    assert severity_from_loss(0.69) == "inaccuracy"
    assert severity_from_loss(0.7) == "inaccuracy"
    assert severity_from_loss(1.49) == "inaccuracy"
    assert severity_from_loss(1.5) == "mistake"
    assert severity_from_loss(2.99) == "mistake"
    assert severity_from_loss(3.0) == "major_mistake"
    assert severity_from_loss(4.99) == "major_mistake"
    assert severity_from_loss(5.0) == "blunder"


def test_severity_from_loss_escalates_for_winrate_collapse() -> None:
    assert severity_from_loss(
        1.2,
        winrate_delta=-0.22,
        winrate_before=0.58,
        winrate_after=0.36,
    ) == "major_mistake"
    assert severity_from_loss(
        1.2,
        winrate_delta=-0.41,
        winrate_before=0.59,
        winrate_after=0.18,
    ) == "blunder"


def _make_result(
    move_number: int,
    played_move: str | None,
    best_move: str,
    estimated_loss: float,
    top_candidates: tuple[CandidateMove, ...],
) -> MoveAnalysisResult:
    to_play = "B" if move_number % 2 == 1 else "W"
    position = PositionInput(
        board_size=19,
        komi=6.5,
        to_play=to_play,
        moves=tuple(),
        played_move=played_move,
    )
    analysis = PositionAnalysis(
        best_move=best_move,
        played_move=played_move,
        estimated_loss=estimated_loss,
        score_estimate=top_candidates[0].score_estimate,
        winrate=top_candidates[0].winrate,
        played_score_estimate=_played_candidate(top_candidates, played_move).score_estimate,
        played_winrate=_played_candidate(top_candidates, played_move).winrate,
        top_candidates=top_candidates,
        pv_summary="",
    )
    return MoveAnalysisResult(
        move_number=move_number,
        color=to_play,
        played_move=played_move,
        recommended_move=best_move,
        estimated_loss=estimated_loss,
        position_input=position,
        engine_analysis=analysis,
    )


def _played_candidate(
    top_candidates: tuple[CandidateMove, ...], played_move: str | None
) -> CandidateMove:
    if not played_move:
        return top_candidates[0]

    for candidate in top_candidates:
        if candidate.move == played_move:
            return candidate

    fallback = top_candidates[-1]
    return CandidateMove(
        move=played_move,
        score_estimate=round(fallback.score_estimate - 0.3, 2),
        winrate=max(0.0, round(fallback.winrate - 0.02, 2)),
    )
