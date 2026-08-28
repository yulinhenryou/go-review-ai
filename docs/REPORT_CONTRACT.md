# M3 Factual Report Contract

Review schema **3.0** replaces 2.2. The HTTP routes remain `/api/v1/*`; route,
payload and product versions are distinct. Update backend and frontend together.
The bundled frontend rejects older report schemas rather than guessing their
meaning. Input preview schema 1.0 and game/engine input semantics are unchanged.

## Selection Policy

- `loss_threshold=3.0`, `severe_threshold=5.0`, `limit=5` by default.
- Both thresholds must be finite, 0-361, with severe >= obvious; limit is an
  integer 1-5. JSON rejects booleans and coercion. Both API routes validate before
  creating the engine. Direct Python review builders use the same validation.
- These are configurable product defaults, **not calibrated universal Go rules**.
  API callers may set both thresholds; the browser uses the defaults in M3.
- Only comparable recommendation/actual-move point estimates from the same
  pre-move position are used. M2 owns matching history/rules/komi/search settings;
  M3 also checks evidence rules, komi, turn, perspective and point units.
- `raw_score_loss = recommended_score - played_score`, in the moving player's
  perspective; `score_loss = max(0, raw_score_loss)`. Raw differences are retained.
  A missing actual candidate in real evidence cannot be substituted by another.
- An obvious mistake has **positive** loss >= loss_threshold. Zero/negative
  differences never become mistakes, including when threshold is zero. Severity
  is `mistake` or `severe`, determined solely by point loss, never winrate.
- Sort selected mistakes by **unrounded** loss descending, then move number
  ascending; take up to limit entries. Never pad the list.

## Result Shape

| Field | Meaning |
| --- | --- |
| `engine_source` | `katago` only when all move/current evaluations carry provenance; injected legacy tests remain `unverified_test_double` |
| `status` | `complete` or `partial` evaluation coverage; NOT a complete-game or confidence claim |
| `summary` | Short Chinese statement of coverage and observed mistake count |
| `game_summary` | Rules, komi, source player/result metadata, record status, input warnings, move and summary-entry counts |
| `coverage` | Total moves, moves with point-loss evidence, exact missing move numbers, equivalent winrate coverage, current-position availability |
| `method` | Actual thresholds/limit, units, perspectives, delta definition and ranking policy |
| `timeline` | All recorded moves in order, including unavailable evaluations |
| `selected_mistakes` | Ranked top-N slice, at most five |
| `review.mistakes_above_threshold` | ALL qualifying mistakes in chronological order, independent of summary limit |
| `current_position` | Recommendation/candidates and available values after the last recorded move; no played-move loss |
| `warnings`, `quality_notes` | Stable warning codes and short Chinese caveats; per-move equivalents remain attached to the evidence |

Each move contains color/number, `played_move`, nullable `recommended_move`,
point loss/raw difference, optional `winrate_delta_pp`, optional scores/winrates,
fixed-black chart values, severity, `is_mistake`, status, candidate-owned PV,
actual candidate, provenance, quality notes and factual summary.

`winrate_delta_pp = 100 * (played_winrate - recommended_winrate)` uses the
**moving player's** perspective. Positive means the searched actual candidate
has a higher estimate, negative lower. Units are **percentage points**, not
relative percent. No rounding occurs until display. This comparison is between
candidate estimates at the pre-move position, not an independently measured
time series. Black-perspective chart fields preserve the M2 normalization.

An actual pass has `played_move.sgf=null` and display `停一手`; an engine pass
recommendation has `sgf="pass"`. A missing recommendation is the whole JSON
value `null`, not a pass. PVs come exclusively from the matching candidate's
structured engine PV; old free-text `pv_summary` is not parsed into moves.

## Missing Evidence and Quality

- Missing comparable point estimates: null loss/severity/is_mistake,
  `status="unavailable"`, exact move number in coverage, no mistake selection.
- Missing winrate only: retain point-loss classification, null delta and black
  winrate, list missing winrate coverage and mark the report partial.
- Missing final-position score or winrate: partial report, retain usable moves.
- Missing PV alone: keep numeric evidence, show an explicit quality note. A
  terminal root evaluation without candidates may still have complete numeric
  coverage; no move or PV is invented.
- An empty top list with partial coverage never describes the entire game as
  clean. `complete` only describes the requested recorded positions; an unfinished
  record stays unfinished/unknown even when every recorded move was evaluated.
- Negative differences, separate played searches and low candidate visits remain
  visible caveats. They are not evidence of tactical causes or objectively good
  moves. Equal search budgets do not imply equal candidate precision.
- Engine startup/protocol/timeout failures still return HTTP 503. M3 does not
  return progress collected before a crashed process; partial reports cover
  successfully received responses with absent numeric fields, not M4 job recovery.

## Retired Fields and Consumers

Removed `key_points`, `classifications`, `explanations`, `training_suggestions`,
per-move categories/teaching labels/swing direction, the duplicate estimated-loss
alias, and ambiguous fractional `winrate_delta`. Use `score_loss` and
`winrate_delta_pp`. Timeline recommendations are now `recommended_move`.
`src/classifier.py`, `src/key_points.py`, `src/chinese_explanations.py` and
`src/user_facing_labels.py`, plus their obsolete tests, are retired from runtime
and packaging; the source remains in Git history and the prototype archive tag.

The text CLI and browser share factual report summaries. The browser shows all
mistake/unavailable markers separately from ranked entries, explicit coverage,
thresholds, provenance and warnings. Selecting a recorded move shows its
**pre-move** board, a red ring for the actual move and a cross for recommendation.
The last recorded move is distinct from the latest-position recommendation.
Charts break across missing move numbers; they do not interpolate missing data.
Queueing, cancellation, editable input snapshots, full manual pass UX and
cross-device deployment remain M4/M5 work.
