# Comparison with the prototype (ROADMAP M4)

Recorded inputs and outputs of the M4 comparison suite: the new single-game
review against the prototype in `legacy/`, on the same engine, model, config
and visits. `python/tests/test_compare_legacy.py` re-runs every check on
these files without an engine, so the evidence outlives `legacy/`.

All games are public or synthetic; their provenance is in
`../sgf/PROVENANCE.md`. Nothing here comes from a private game.

## Files

| File | What it is |
| --- | --- |
| `legacy-<game>-1.json`, `-2.json` | Two independent prototype reviews of each game (`comparison.legacy.v1`, written by `legacy/scripts/export_review.py review`) |
| `tolerances.json` | The prototype's run-to-run spread and the pass lines derived from it, recorded before any new run was compared |
| `new-<game>.json` | One new review of each game, reduced to the same shape (`comparison.new.v1`, `weiqi.tools.compare_legacy reduce-new`) |
| `cases.json` | 26 inputs for the accept/reject comparison: the corpus files and 19×19 hand-written cases |
| `legacy-decisions.json`, `new-decisions.json` | Each side's decision on every case |

## How they were made

On 2026-11-09, on the owner's Apple M4 Mac: KataGo 1.18.2 (Metal), model
`kata1-b18c384nbt-s9996604416-d4316597426` (SHA-256 `9d7a6afe…`), the
shared `config/katago/analysis.cfg` (SHA-256 `ff7bcc30…`, byte-identical to
the prototype's), 200 visits. The prototype's query overrides
(`playoutDoublingAdvantage` 0, `antiMirror` false) are KataGo's defaults.

```bash
# In legacy/ (the prototype's environment), twice per game:
KATAGO_MODEL_PATH=… KATAGO_CONFIG_PATH=../config/katago/analysis.cfg \
  .venv/bin/python -m scripts.export_review review ../testdata/sgf/<game>.sgf \
  --visits 200 --output legacy-<game>-<n>.json
.venv/bin/python -m scripts.export_review decide ../testdata/comparison/cases.json \
  --output legacy-decisions.json

# In python/, once per game, each with an empty database:
uv run python -m weiqi.review ../testdata/sgf/<game>.sgf --database sqlite:///new.db \
  --visits 200 --format json --output result.json
uv run python -m weiqi.tools.compare_legacy reduce-new result.json --sgf-name <game>.sgf \
  --output new-<game>.json
uv run python -m weiqi.tools.compare_legacy decide ../testdata/comparison/cases.json \
  --output new-decisions.json
uv run python -m weiqi.tools.compare_legacy check ../testdata/comparison
```

## What is compared

The prototype's score loss is a same-root loss: the best candidate minus the
played move, with a restricted search when the played move was not searched.
It is compared with the new same-root diagnostic (ADR-P02), in clamped
points. Mistake sets use the prototype's 3-point line and its top-five
ranking, computed the same way for both sides (the selection reproduces the
prototype's own lists in all eight runs).

**Noise first.** The prototype's two runs of each game differed by at most
0.002 points on half of the 356 moves, by at most 0.464 points on 95% of them
(pooled), and by up to 9.65 points on one move (Ke Jie game, move 106: one
run recommended the played move, the other a different move). Mistake sets
agreed completely on three games; on the Ke Jie game the moves at or above
3 points overlapped 0.667 (Jaccard) and the top five 0.5.

**Pass lines** (chosen by the owner from those numbers, before the new runs):

- per move, pooled over all games, against each prototype run: at least 90%
  of moves within 0.464 points (the prototype against itself: 95%);
- per game, against each prototype run: set overlap (moves at or above
  3 points, and the top five) at least the prototype's own overlap minus 0.25;
- every case the prototype accepts is accepted; a case only the new review
  accepts needs a recorded reason (`NEW_ALSO_ACCEPTS`);
- every prototype warning code has a new equivalent (`WARNING_EQUIVALENTS`).

## Result (2026-11-09)

All checks passed.

| | New vs prototype run 1 | New vs prototype run 2 |
| --- | --- | --- |
| Moves within 0.464 points (pooled, 356) | 96.4% | 94.7% |
| Median / 95th percentile difference | 0.000 / 0.414 | 0.000 / 0.511 |
| Largest difference | 1.64 | 9.65 (Ke Jie move 106; the new review agrees with run 1) |

Per game, the share within 0.464 points was 97–100% on three games and
91.9% / 89.2% on the Ke Jie game, where the prototype against itself
reached 90.1%. Mistake sets: identical on the sample, `m3-mistake` and the
235-move game (moves 1, 3, 5 and move 83); on the Ke Jie game the new
review's moves at or above 3 points were 60, 93 and 94, against 54, 60, 93
and 94 (overlap 0.75) and 54, 60, 93, 94, 96 and 106 (0.5).

Decisions: identical on 17 of 26 cases. The new review also accepts nine
cases the prototype refuses as unsupported: a GBK file without `CA`, a
declared GB2312 file, text before the game, an unclosed tree, play after two
passes, White moving first, handicap setup stones, a 9×9 board and Korean
rules. Rule violations (ko, suicide, two moves of one colour) and games
without moves are refused by both (ADR-P19).
