# M2 Engine Contract

Implemented against KataGo 1.16.4 and the
[official JSON analysis protocol](https://github.com/lightvector/KataGo/blob/master/docs/Analysis_Engine.md).
This is a real-engine adapter, not a claim that the whole web product is complete.

## Lifecycle and Readiness

`engine_factory.build_default_engine()` requires explicit `KATAGO_MODEL_PATH` and
`KATAGO_CONFIG_PATH`. `KATAGO_PATH` defaults to `katago`. Missing configuration,
unreadable/empty files, process startup failure or timeout never select mock data.
Deterministic prototype data now lives only in `tests/mock_engine.py`; it is not
in the application wheel or any production import.

One game uses one model-loaded process. Positions are submitted in batches of at
most 16 turns using `analyzeTurns`; missing played moves are requested in a second
batch with `allowMoves` restricted at root depth 1. Batch requests preserve the
original history, rules, komi, maxVisits and evaluation settings.
The standalone position method opens/closes its own session; a client context
manager explicitly allows repeated position queries with the same process.

The POSIX transport uses nonblocking pipes and drains stderr. It handles fragmented
JSONL, interim output, out-of-order final responses, warnings, errors and process
exit. Every final response must match a pending `(id, turnNumber)` pair. Unknown
or duplicate replies fail closed. A JSONL line is capped at 4 MiB. A batch has an
absolute deadline of 60 seconds times its position count by default. Readiness
has a 60-second deadline. Timeout/failure closes pipes and terminates/reaps the
process, escalating to kill after 2 seconds. Successful game completion also
reaps the process. No uploaded game is retained by the adapter.

Readiness validates files and queries the version and loaded model. `/health`
remains liveness only; `/ready` performs a fresh model-load check and is relatively
expensive. Do not poll it frequently. Readiness is not a game-quality benchmark.
Windows, a shared worker between games, bounded API job concurrency, cancellation
and caching/readiness orchestration remain outside M2.

## Numeric Evidence

- The process is forced to report BLACK perspective. Candidate `score_black`
  and `winrate_black` preserve those raw values.
- Compatibility fields `score_estimate` and `winrate` use the player to move.
  White values are `-black_score` and `1-black_winrate`.
- The recommendation uses KataGo's `order=0`, not array order or the maximum
  score of a shallow candidate. Point loss compares that recommendation with
  the actual evaluated move from the same pre-move position.
- `raw_score_loss = recommended_score - played_score` in moving-player units;
  `estimated_loss = max(0, raw_score_loss)`. No pre-ranking rounding. Negative
  differences remain recorded and flagged as possible search noise.
- Only `scoreLead` is accepted as points. Missing score/winrate stays null;
  utility is never used as a score, and missing winrate is never 50 percent.
  Nonfinite numbers, booleans and invalid values are protocol failures.
- An absent/unvisited/unscored actual move triggers explicit restricted search,
  including pass. If still unavailable, loss stays null. Separate searches and
  low candidate visits are quality warnings, not evidence of a tactical cause.
  Equal root budgets do not imply equal candidate visits or equal certainty.
- A current-position request has no played evaluation and no move loss. Empty
  candidate lists may retain genuine root values but never fabricate a move.
- Each candidate owns its actual ordered PV as `{color, move}` entries. Missing
  PV is empty. No padding, alternative-candidate stitching or borrowed PVs.

## Historical Review Schema 2.2

The existing report fields remain for compatibility. Added fields include:

- `engine_source`: `katago`, or `unverified_test_double` for injected tests.
- Candidate PV, visits and fixed-black values.
- Timeline `score_black_before/after`, `winrate_black_before/after`, unrounded
  raw loss, actual candidate evidence and per-position provenance.
- Provenance: version, model internal identifier/SHA-256, config SHA-256, rules,
  komi, max visits, root visits, request ID, turn, played-search ID/source,
  warnings and elapsed seconds for the whole containing batch (not per turn).
  Hashes identify local files without publishing their paths or contents.

The frontend charts now use fixed-black data; candidate details display that
candidate's own PV. Existing moving-player fields retain their prior semantics.
Winrate fields are fractions, not percentage points.

M2's old report rejected incomplete evidence with HTTP 503 `incomplete_analysis`.
M3 supersedes that boundary: successfully received responses with missing numeric
evidence produce schema 3.0 partial reports and explicit coverage. Missing PVs are
flagged rather than fabricated. Unavailable engine still returns `engine_unavailable`;
other engine/protocol failures return `analysis_failed`. No raw error/path is
returned to the browser. See [report contract](REPORT_CONTRACT.md) for the current
fields, units and missing-evidence semantics.

## Still Not a Release

M3 now provides factual templates, obvious-mistake thresholds, quality/coverage
presentation and retirement of unsupported teaching heuristics. M4 owns bounded jobs and full
input/report UI. The API is still a loopback development service, not suitable for
public expensive-analysis traffic. Pages still hosts only the older static preview.
