"""Locale catalogs and the text report (MIGRATION R07, R08): the same keys
and placeholders in every language, an entry for every code a result can
carry, and a report that only rewords what the result holds."""

from __future__ import annotations

import re
import string
from dataclasses import replace

import pytest
import weiqi_core
from review_fixtures import OTHER, ROOTS, review

from weiqi.explain import LOCALES, load_catalog, render_report
from weiqi.metrics import GroupStatusChange
from weiqi.metrics.loss import (
    LOW_VISITS_FLAG,
    MISSING_SCORE,
    MISSING_WINRATE,
    NEGATIVE_NOISE,
    NOT_SEARCHED,
    SEPARATE_SEARCH,
)
from weiqi.review import RULE_NAMES

CJK = re.compile(r"[一-鿿]")


def placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_every_locale_has_the_same_keys_and_placeholders() -> None:
    zh, en = (load_catalog(locale).entries for locale in LOCALES)
    assert zh.keys() == en.keys()
    for key in zh:
        assert placeholders(zh[key]) == placeholders(en[key]), key
    assert not any(CJK.search(text) for text in en.values())


def test_every_code_a_result_carries_has_an_entry() -> None:
    codes = (
        [f"color.{c}" for c in ("B", "W")]
        + [f"severity.{s}" for s in ("mistake", "severe")]
        + [f"status.{s}" for s in ("complete", "partial")]
        + [f"record_status.{s}" for s in ("result_recorded", "unfinished_or_unknown")]
        + [f"group.{s}" for s in ("alive", "dead", "unsettled", "captured")]
        + [f"band.{b}" for b in ("black_ahead", "close", "white_ahead")]
        + [f"rules.{name}" for name in RULE_NAMES]
        + [
            f"replay.{code}"
            for code in (
                "out_of_turn",
                "ko_violation",
                "superko_violation",
                "suicide",
                "repeated_position",
            )
        ]
        + [
            f"flag.{flag}"
            for flag in (
                MISSING_SCORE,
                MISSING_WINRATE,
                NEGATIVE_NOISE,
                NOT_SEARCHED,
                SEPARATE_SEARCH,
                LOW_VISITS_FLAG,
                "missing_current_value",
                "no_candidate_moves",
                "recommendation_unavailable",
                "missing_pv",
            )
        ]
    )
    for locale in LOCALES:
        catalog = load_catalog(locale)
        assert [code for code in codes if not catalog.has(code)] == [], locale


def test_an_unknown_locale_is_refused() -> None:
    with pytest.raises(ValueError, match="locale"):
        load_catalog("fr")


@pytest.mark.parametrize("locale", LOCALES)
def test_the_report_rewords_the_results_numbers(locale: str) -> None:
    result = review()
    text = render_report(result, locale)
    assert "{" not in text and "}" not in text
    gtp = {m.move_number: weiqi_core.to_gtp(m.move, 19, 19) for m in result.timeline[:3]}
    # Ranked order: move 2 (9.0, severe), move 1 (5.0), move 4 (a pass, 4.0).
    positions = [text.index(f"{loss:.1f}") for loss in (9.0, 5.0, 4.0)]
    assert positions == sorted(positions)
    assert gtp[1] in text and gtp[2] in text
    assert weiqi_core.to_gtp(OTHER, 19, 19) in text
    assert load_catalog(locale).text("move.pass") in text
    assert "Alice" in text and "B+R" in text
    assert result.engine.model_sha256 in text and result.engine.config_sha256 in text
    if locale == "en":
        assert not CJK.search(text)


def test_a_partial_result_says_so_and_names_the_missing_moves() -> None:
    text = render_report(review([ROOTS[0], None, *ROOTS[2:]]), "en")
    assert load_catalog("en").text("report.partial") in text
    assert "Moves without score evidence: 1, 2" in text
    assert load_catalog("en").text("report.clean") not in text


def test_unknown_codes_are_shown_as_codes_not_dropped() -> None:
    result = review(warnings={1: ("someEngineField",)})
    sgf = b"(;FF[4]GM[1]SZ[19]RU[Chinese]KM[7.5]HA[2];B[pd];W[dd];B[pp];W[])"
    for locale in LOCALES:
        assert "someEngineField" in render_report(result, locale)
        noted = render_report(review(sgf=sgf), locale)
        # handicap_mismatch has its own entry; any other input code falls back.
        assert load_catalog(locale).text("input.handicap_mismatch") in noted


def test_group_changes_and_turning_points_are_listed() -> None:
    result = review()
    assert result.turning_points
    stones = tuple((x, 0) for x in range(8))
    change = GroupStatusChange("W", stones, "alive", "dead", 0.9, -0.8)
    timeline = tuple(
        replace(m, group_changes=(change,)) if m.move_number == 2 else m for m in result.timeline
    )
    text = render_report(replace(result, timeline=timeline), "en")
    assert "White A19 B19 C19 D19 E19 F19 … (8 stones): alive → dead" in text
    assert "Turning points" in text
    for point in result.turning_points:
        assert f"Move {point.move_number}," in text


def test_replay_warnings_are_listed_by_move() -> None:
    # Only `repeated_position` reaches a result (rule violations are refused),
    # but every replay code renders.
    result = review()
    noted = replace(result, game=replace(result.game, replay_warnings=((3, "repeated_position"),)))
    en = load_catalog("en")
    expected = en.text("report.replay_warning", number=3, text=en.text("replay.repeated_position"))
    assert expected in render_report(noted, "en")
