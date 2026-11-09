"""The plain-text review report (MIGRATION R07), rendered from a
`ReviewResult` in one locale. It reorders and words what the result holds;
every number and coordinate comes from the result."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

import weiqi_core

from weiqi.explain.catalog import Catalog, load_catalog

if TYPE_CHECKING:
    from weiqi_core import Move, Point

    from weiqi.review.result import ReviewResult

_MAX_STONES_SHOWN = 6


def render_report(result: ReviewResult, locale: str = "zh-CN") -> str:
    c = load_catalog(locale)
    game, coverage, method = result.game, result.coverage, result.method

    def move(value: Move | None) -> str:
        if value is None:
            return c.text("move.none")
        if value == "pass":
            return c.text("move.pass")
        return weiqi_core.to_gtp(value, game.width, game.height)

    def stones(points: Sequence[Point]) -> str:
        shown = " ".join(move(p) for p in points[:_MAX_STONES_SHOWN])
        return shown + (" …" if len(points) > _MAX_STONES_SHOWN else "")

    unknown = c.text("report.unknown_player")
    lines = [
        c.text("report.title"),
        "- "
        + c.text(
            "report.players", black=game.black_player or unknown, white=game.white_player or unknown
        ),
        "- "
        + c.text(
            "report.board",
            width=game.width,
            height=game.height,
            rules=c.text(f"rules.{game.rules}"),
            komi=f"{game.komi:g}",
        ),
        "- "
        + c.text(
            "report.result",
            result=game.result_text or c.text("report.no_result"),
            record_status=c.text(f"record_status.{game.record_status}"),
        ),
        "- "
        + c.text(
            "report.coverage",
            with_score=coverage.moves_with_score,
            with_winrate=coverage.moves_with_winrate,
            with_ownership=coverage.moves_with_ownership,
            total=coverage.moves_total,
            mistakes=sum(m.severity is not None for m in result.timeline),
        ),
    ]
    if result.status == "partial":
        lines.append("- " + c.text("report.partial"))
    elif not any(m.severity for m in result.timeline):
        lines.append("- " + c.text("report.clean"))
    lines.append(
        "- "
        + c.text(
            "report.method",
            mistake=f"{method.mistake_threshold:g}",
            severe=f"{method.severe_threshold:g}",
        )
    )

    lines += ["", c.text("report.mistakes")]
    if not result.mistakes:
        lines.append(c.text("report.no_mistakes"))
    by_number = {m.move_number: m for m in result.timeline}
    for ranked in result.mistakes:
        item = by_number[ranked.move_number]
        color = c.text(f"color.{item.color}")
        winrate = (
            c.text("move.none")
            if item.winrate_delta_pp is None
            else c.text("report.winrate_pp", value=item.winrate_delta_pp)
        )
        lines.append(
            "- "
            + c.text(
                "report.mistake",
                severity=c.text(f"severity.{ranked.severity}"),
                number=item.move_number,
                color=color,
                move=move(item.move),
                loss=f"{ranked.score_loss:.1f}",
                winrate=winrate,
                best=move(item.best_move),
            )
        )
        if item.pv:
            lines.append("  " + c.text("report.pv", pv=" ".join(move(m) for m in item.pv)))
        for change in item.group_changes:
            lines.append(
                "  "
                + c.text(
                    "report.group_change",
                    color=c.text(f"color.{change.color}"),
                    stones=stones(change.stones),
                    size=len(change.stones),
                    before=c.text(f"group.{change.before}"),
                    after=c.text(f"group.{change.after}"),
                )
            )

    if result.turning_points:
        lines += ["", c.text("report.turning_points")]
        for point in result.turning_points:
            item = by_number[point.move_number]
            lines.append(
                "- "
                + c.text(
                    "report.turning_point",
                    number=point.move_number,
                    color=c.text(f"color.{point.color}"),
                    move=move(item.move),
                    before=c.text(f"band.{point.band_before}"),
                    after=c.text(f"band.{point.band_after}"),
                    rate_before=f"{point.winrate_black_before:.0%}",
                    rate_after=f"{point.winrate_black_after:.0%}",
                )
            )

    engine = result.engine
    lines += [
        "",
        c.text(
            "report.source",
            version=engine.version,
            model=engine.model_name,
            visits=engine.max_visits,
        ),
        c.text("report.model_hash", sha=engine.model_sha256),
        c.text("report.config_hash", sha=engine.config_sha256),
    ]
    notes = _notes(c, result)
    if notes:
        lines += ["", c.text("report.notes"), *("- " + note for note in notes)]
    return "\n".join(lines)


def _notes(c: Catalog, result: ReviewResult) -> list[str]:
    notes = []
    for code in result.game.input_warnings:
        key = f"input.{code}"
        if c.has(key):
            notes.append(c.text(key, encoding=result.game.encoding))
        else:
            notes.append(c.text("input.other", code=code))
    for number, code in result.game.replay_warnings:
        key = f"replay.{code}"
        text = c.text(key) if c.has(key) else c.text("replay.other", code=code)
        notes.append(c.text("report.replay_warning", number=number, text=text))
    for code in result.warnings:
        key = f"flag.{code}"
        notes.append(c.text(key) if c.has(key) else c.text("flag.other", code=code))
    if result.coverage.missing_score_moves:
        moves = ", ".join(map(str, result.coverage.missing_score_moves))
        notes.append(c.text("report.missing_moves", moves=moves))
    return notes
