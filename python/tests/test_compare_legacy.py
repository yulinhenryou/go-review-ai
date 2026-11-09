"""The comparison suite's own logic on hand-written runs: quantiles, the
prototype's selection, set agreement, guards against comparing different
games or engines, the reduction of a new result, and the warning map."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from review_fixtures import review

from weiqi.explain import LOCALES, load_catalog
from weiqi.tools.compare_legacy import (
    WARNING_EQUIVALENTS,
    Run,
    above_threshold,
    check_decisions,
    check_report,
    compare_runs,
    envelope_report,
    jaccard,
    load_run,
    new_decisions,
    quantile,
    reduce_new,
    top_mistakes,
)

ENGINE = ("1.18.2", "a" * 64, "b" * 64, 200)
RECORDED = Path(__file__).parents[2] / "testdata" / "comparison"


def run(losses: dict[int, float | None], engine: tuple[str, str, str, int] = ENGINE) -> Run:
    moves = tuple((n, "B" if n % 2 else "W", "pd") for n in sorted(losses))
    return Run("legacy", "c" * 64, engine, moves, losses)


def test_quantiles_are_observed_values_by_nearest_rank() -> None:
    values = [float(v) for v in range(1, 21)]  # 1..20
    assert quantile(values, 0.5) == 10.0
    assert quantile(values, 0.95) == 19.0
    assert quantile(values, 1.0) == 20.0
    assert quantile([3.0], 0.9) == 3.0
    with pytest.raises(ValueError):
        quantile([], 0.5)


def test_the_prototype_selection_ranks_by_loss_then_move_and_never_pads() -> None:
    # Prototype ADR-004: unrounded loss descending, then move number.
    losses: dict[int, float | None] = {1: 3.0, 2: 9.0, 3: 2.99, 4: 9.0, 5: None, 6: 4.0}
    assert top_mistakes(run(losses)) == (2, 4, 6, 1)
    many = run({n: 10.0 + n for n in range(1, 9)})
    assert top_mistakes(many) == (8, 7, 6, 5, 4)


def test_set_agreement() -> None:
    assert jaccard([], []) == 1.0
    assert jaccard([1, 2], [2, 3]) == pytest.approx(1 / 3)


def test_pair_statistics_skip_missing_values() -> None:
    a = run({1: 0.0, 2: 5.0, 3: None, 4: 1.0})
    b = run({1: 0.5, 2: 3.5, 3: 2.0, 4: 1.0})
    stats = compare_runs(a, b)
    assert stats.compared == 3
    assert stats.differences == (0.5, 1.5, 0.0)
    assert stats.share_within(0.5) == pytest.approx(2 / 3)
    assert stats.above_threshold_jaccard == 1.0  # {2} and {2}


def test_runs_of_different_games_or_engines_are_not_compared() -> None:
    with pytest.raises(ValueError, match="same game"):
        compare_runs(run({1: 0.0}), run({1: 0.0, 2: 0.0}))
    other = ("1.16.4", *ENGINE[1:])
    with pytest.raises(ValueError, match="different engines"):
        compare_runs(run({1: 0.0}), run({1: 0.0}, other))


def test_a_new_result_is_reduced_to_the_prototype_shape() -> None:
    result = json.loads(review().to_json())
    document = reduce_new(result, "fixture.sgf")
    reduced = load_run(document)
    assert reduced.source == "new"
    # SGF letters, a pass as None, and the same-root value as the loss.
    assert [m[2] for m in reduced.moves] == ["pd", "dd", "pp", None]
    assert [m["sequential_score_loss"] for m in document["moves"]] == [5.0, 9.0, 1.0, 4.0]
    assert list(reduced.losses.values()) == [m["same_root_score_loss"] for m in result["timeline"]]


def test_every_prototype_warning_has_an_equivalent_with_text() -> None:
    assert len(WARNING_EQUIVALENTS) == 14
    for legacy, codes in WARNING_EQUIVALENTS.items():
        assert codes or legacy == "unverified_engine"
        for locale in LOCALES:
            catalog = load_catalog(locale)
            for code in codes:
                assert catalog.has(f"flag.{code}") or catalog.has(f"input.{code}"), code


# --- The recorded comparison (testdata/comparison, real engine runs) ---


def recorded(name: str) -> Any:
    return json.loads((RECORDED / name).read_text(encoding="utf-8"))


def test_the_selection_reproduces_the_prototypes_own_lists() -> None:
    files = sorted(RECORDED.glob("legacy-*-[12].json"))
    assert len(files) == 8
    for path in files:
        document = recorded(path.name)
        legacy = load_run(document)
        assert list(top_mistakes(legacy)) == document["selected_mistakes"], path.name
        assert sorted(above_threshold(legacy)) == document["mistakes_above_threshold"]


def test_the_recorded_tolerances_come_from_the_recorded_prototype_runs() -> None:
    tolerances = recorded("tolerances.json")
    assert tolerances["envelope"] == envelope_report(RECORDED)
    assert tolerances["loss_tolerance_points"] == tolerances["envelope"]["pooled"]["p95"]
    assert (tolerances["min_share_within"], tolerances["set_slack"]) == (0.9, 0.25)


def test_the_new_decisions_are_current_and_agree_with_the_prototype() -> None:
    current = new_decisions(RECORDED / "cases.json")
    assert current == recorded("new-decisions.json")
    assert check_decisions(recorded("legacy-decisions.json"), current) == []


def test_a_refusal_of_a_supported_input_is_a_problem() -> None:
    legacy = [{"name": "a", "accepted": True, "code": None}]
    new = [{"name": "a", "accepted": False, "code": "x", "warnings": []}]
    assert check_decisions(legacy, new) == ["a: refused (x), the prototype accepts it"]


def test_the_recorded_comparison_passes() -> None:
    report = check_report(RECORDED)
    assert report["problems"] == []
    assert report["passed"]
