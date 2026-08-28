# V1 Development Path

**Status: approved on 2026-08-27; M1-M4 implemented locally, M4 verified on 2026-08-29.**
Prepared on 2026-08-27 after auditing prototype `7447f54`.
M1 was reverified and uploaded at d08fc47 after GitHub access recovery.
M2 implementation and real-engine evidence are recorded in [M2 acceptance](M2_ACCEPTANCE.md).
M3 evidence is recorded in [M3 acceptance](M3_ACCEPTANCE.md).
M4 evidence is recorded in [M4 acceptance](M4_ACCEPTANCE.md). M5 is not implemented.

## Release Goal

A user uploads an SGF or enters a game move by move on a web board. The system
validates the game, runs real KataGo, marks obvious mistakes, and displays a short
report whose numbers and recommendations can be traced to engine output.

A static board, mock report, or successful unit-test run alone is not v1.
The local workflow is an intermediate milestone; the release requires a deployed
backend that another device can reach.

## Proposed Scope

| Include in v1 | Defer until after v1 |
| --- | --- |
| One standard 19x19 game per analysis | Batch games, accounts, saved-game library |
| UTF-8 SGF, optional BOM; first variation with an explicit notice | Other encodings and interactive variation-tree editing |
| Board-based manual entry, pass, undo, clear, player names, rules and komi | Arbitrary text notation import and setup-position editor |
| Chinese and Japanese rules selected explicitly or read from SGF | Other rulesets, handicap and setup-stone games |
| Actual move and recommendation markers; previous/next move | Interactive variation exploration beyond a short engine PV |
| Top 5 obvious mistakes plus chronological mistake markers | Automated tactical causes, training plans, teaching labels and LLM commentary |
| Concise Chinese report; engine provenance and honest failure states | Database, Redis/Celery cluster, paid accounts |

Manual entry means clicking the board in sequence, not setting up an arbitrary
position. A partial game is allowed and must be labeled as partial; do not infer
a final result or a missing game phase.

Unsupported input must fail explicitly. Do not silently ignore nonzero handicap,
setup properties (`AB/AW/AE`), unsupported turn overrides, multiple-game collections,
or other board sizes. Missing rules/komi require a user-confirmed choice before
analysis, rather than a hidden engine default. Comments and unrelated metadata
may be ignored safely; properties affecting position or rules may not.

Initial resource limits to implement and verify: 1 MiB SGF, 1-500 main-line moves,
finite validated komi/thresholds, one running engine job and a small bounded queue.
These are proposed application limits, not statements about KataGo's capability.
Confirm concrete queue size, timeout and retention settings with M2 benchmarks.

## Architecture Direction

Retain Python, FastAPI, vanilla JavaScript and the existing separation of concerns.
Do not add a frontend framework just to reorganize the prototype.

```text
Web input
  -> SGF adapter / manual-moves adapter
  -> one validated GameRecord
  -> review job
  -> KataGo adapter
  -> normalized evaluations
  -> mistake selector + factual templates
  -> versioned ReviewResult
  -> browser board + concise report
```

Suggested responsibility boundaries, not a request to create empty modules:

| Boundary | Rule |
| --- | --- |
| Game model and validation | Own rules, turn order, legal positions and coordinate conversion |
| SGF adapter | Parse into the shared model; no engine calls or report prose |
| Engine adapter | Own process lifecycle and raw JSONL mapping; no Go teaching claims |
| Analysis | Normalize evidence, score perspectives and quality flags |
| Selection/classification | Threshold and severity only for the v1 default report |
| Reporting | Serialize evidence and fill deterministic factual templates |
| API/jobs | Validate requests, manage bounded work, expose status and cancellation |
| Frontend | Present input/report states; do not invent missing evaluations |

The API should call a shared review service rather than depend on CLI setup.
Move the orchestration out of `src/main.py` when changing that boundary, keeping
a thin CLI adapter. Avoid a wholesale rename of every module at once.

## M0 - Establish the Baseline

Deliverables for this housekeeping pass:

- Inventory the source and document known release blockers.
- Archive the two unused generated report snapshots without changing their bytes.
- Preserve the entire prototype through its existing GitHub baseline commit and
  tag `archive/prototype-2026-08-27`, uploaded after authentication recovery.
- Clarify the roles of active source, samples, tests, archived output and Pages.
- Update README and AGENTS to distinguish the historical CLI phase from web v1.
- Ignore local credentials, private uploads, model files and generated outputs.

Gate: same 54 regression tests pass, runtime source is unchanged, archive contents
are preserved, documentation links resolve, and the changes are on GitHub.
Runtime mock/heuristic isolation is deliberately deferred to M2/M3 because it
changes behavior. The user has now approved functional development.
Verification and GitHub synchronization are complete. See [the status audit](PROJECT_STATUS.md).

## M1 - Normalize and Validate Inputs

Dependencies: M0 and approval of this plan.

Delivered: shared immutable records, sgfmill adapters and replay validation,
preview endpoints, strict pre-engine input boundaries, explicit pass context,
rule propagation, versioned result metadata and verified packaging.
Details: [input contract](INPUT_CONTRACT.md) and [acceptance evidence](M1_ACCEPTANCE.md).

Work:

- Define `GameRecord` and review-contract semantics: board size, rules, komi, players, main-line
  moves, pass representation and game result. Distinguish an actual pass from
  "no played move" in current-position analysis requests.
- Use [sgfmill](https://github.com/mattheww/sgfmill) 1.1.1 under a small adapter.
  Its Board handles captures; the application enforces turn order, no suicide,
  simple ko and the supported input boundary with fixtures. This is not a full
  tournament adjudication/scoring implementation.
- Route SGF and manual moves through one server-side legality validator.
- Handle root-node moves, empty/pass moves, first variation, invalid syntax,
  out-of-range coordinates, unsupported properties and input-size limits.
- Specify request, result and error contracts before changing the UI. Version
  schema changes and update consumers together; keep product version separate.
- Establish explicit package discovery, exclude archives from distributions, and
  verify installation and tests in a clean environment with recorded dependencies.

Gate: equivalent SGF/manual input gives the same normalized moves, metadata and
positions; capture/ko/pass fixtures replay correctly; malformed or unsupported
input never reaches KataGo. Existing small SGF tests stay meaningful, not just green.

## M2 - Make Real Analysis Trustworthy

Dependencies: M1's validated model and rules semantics.

Delivered: real-only factory, model readiness, one process per game, bounded
turn batches, ID/turn matching, fixed-black evidence, actual-move search, genuine
PVs, failure cleanup, recorded-response replay and live benchmarks. See
[engine contract](ENGINE_CONTRACT.md) for the conservative missing-data boundary.

Work:

- Check binary/model/config readiness. The production path must report an error
  when unavailable; never automatically substitute mock analysis.
- Move deterministic mock behavior to test fixtures or an explicit demo entry
  outside production imports. Preserve coverage of former adapter helpers.
- Reuse a loaded model for a game's positions; consume complete JSONL responses,
  including error/warning records, and match final results by request ID and turn.
- Fix or explicitly normalize analysis perspective. Store a fixed black perspective
  for charts; compute move loss from the player who actually made the move.
- Use actual evaluated moves: if the played move is absent, request its evaluation
  with the same rules, komi, perspective and search budget. Missing evidence remains
  unavailable; it is never estimated from another candidate's score.
- Only use score values in point units. Missing scores/winrates/PVs stay missing,
  not utility-as-points, 50% defaults, candidate lists as sequences or padded passes.
- Keep genuine PVs as structured moves belonging to their own candidate.
- Record engine version, model identifier/hash, rules, komi, visits, perspective,
  elapsed time and warnings without exposing local absolute paths or configuration.
- Handle end-of-game positions, timeouts, malformed output, engine exit and cleanup.

Gate: recorded-response tests cover both players, missing played moves, pass,
nonfinite/missing fields, absent PV, out-of-order messages and engine failure.
An opt-in integration test runs a small valid game against real KataGo; the result
is not a fixed mock. Save a sanitized evidence fixture and its provenance.

Use the [official analysis protocol](https://github.com/lightvector/KataGo/blob/master/docs/Analysis_Engine.md)
to specify batching and response matching. Benchmark a short game and a typical
200-300 move game on named hardware/model/search settings; record time and memory.
Do not promise a fixed response time before these measurements.

## M3 - Select Obvious Mistakes and Write a Factual Report

Dependencies: M2's evaluated move evidence.

Delivered: schema 3.0 factual Chinese templates, coverage-aware partial reports,
point-only severity, ranked top-five summary, all chronological mistake markers,
candidate-owned PVs, visible provenance/warnings, and retired heuristic modules.
CLI/API/frontend consumers are migrated together. See [report contract](REPORT_CONTRACT.md)
and [M3 acceptance](M3_ACCEPTANCE.md). The [M1-M3 regression record](M1_M3_REGRESSION.md)
covers this source update. Public deployment remains M5 work.

Implemented initial selection policy (still requires calibration):

- Start with estimated point loss >= 3.0 as an obvious mistake and >= 5.0 as a
  severe mistake. These are configurable product defaults to calibrate, not
  established universal Go rules. M3 replaces the older 1.0/3-entry defaults.
- Compute `loss = max(0, recommended_score - played_score)` only after scores have
  the same moving-player perspective and comparable search context.
- Preserve raw differences and quality warnings. A negative difference can reflect
  search noise; do not turn it into an invented positive teaching claim.
- Sort by unrounded loss descending, break ties by move number, display at most
  five entries. No forced padding when fewer or no qualifying mistakes exist.
- Express winrate changes in percentage points with an explicit player perspective.
  Do not use winrate alone to infer a tactical cause or severe error.

Work:

- Keep all per-move markers separate from the top-five summary.
- Each mistake includes move number/color, actual move, recommendation, point loss,
  available winrate change, and genuine candidate PV when present.
- Use short templates equivalent to "Move 83, Black: K10; recommended D4;
  estimated loss 4.2 points." Example numbers illustrate the format, not a result.
- Show missing-evidence, partial-result and no-obvious-mistake states explicitly.
  Incomplete evaluation must not be described as a fully clean game.
- Remove unsupported direction/overplay/main-battlefield/plan-break narratives from
  the default report. Retire obsolete consumers and tests together; do not leave
  unused teaching modules imported by production. Their source remains in Git.
- Keep a summary of metadata, coverage, method/threshold and top mistakes; skip
  invented phase summaries, diagnoses and broad training advice.

Gate: threshold boundaries, ordering ties, zero/fewer-than-five mistakes, both
player perspectives and missing data are tested with fixed engine evidence.
The report cannot name a tactical cause solely from distance, rank or move number.
Real-engine reruns use tolerances; only fixture transformations must be exact.

## M4 - Complete the Browser Workflow

Dependencies: M1 contracts, M2 engine lifecycle and M3 report semantics.

Delivered locally: modular browser input/review, shared replay snapshots,
preview/confirmation, pass/undo/clear, bounded ephemeral jobs, progress,
cancellation, refresh recovery and exact-origin configuration. See the
[job contract](JOB_CONTRACT.md) and [acceptance evidence](M4_ACCEPTANCE.md).

Work:

- Split the existing HTML into board/state, API, report-rendering and style units
  as those units are tested. Keep the current UI as a reference in the archive tag.
- Provide upload preview and metadata confirmation before analysis; provide manual
  placement, pass, undo and clear using consistent board/rules validation.
- Implement bounded analysis jobs outside the request/event loop. Start with one
  application instance and an in-memory job store; do not require a database.
- Proposed API: submit validated input -> job ID; poll status/result; cancel job.
  States: queued, running, succeeded, failed, cancelled. Progress counts analyzed
  positions and never pretends a partial result is complete.
- Keep a stable input snapshot per job; ignore late responses after input changes.
  Cancellation must release engine work and capacity. On restart, clearly mark old
  jobs unavailable and allow resubmission. Expire stored results and raw uploads.
- Show the concise report beside the board. Clicking a mistake shows the position
  immediately before that move and clearly distinguishes actual/recommended points.
- Provide loading, validation, unavailable-engine, timeout, cancellation, queue-full,
  incomplete-analysis and empty-result states without requiring raw JSON inspection.
- Prefer same-origin API URLs for the full app. Allow explicit HTTPS API configuration
  for Pages if retained; configure exact allowed origins, not wildcard CORS.

Gate: browser tests actually exercise SGF upload and manual entry through the API,
pass/undo, error recovery, selecting a mistake, move navigation and stale responses.
Check desktop and mobile layouts. Mock tests cover failures; at least one full
browser workflow must also run through real KataGo. The old string-presence test
is not sufficient acceptance coverage.

## M5 - Deploy and Accept the Release

Dependencies: M4 and approved backend hosting resources.

Preferred topology: one HTTPS origin serving the frontend and FastAPI, with a
KataGo worker in the backend environment. Pages may remain a separate static preview.
[GitHub Pages hosts static files](https://docs.github.com/en/pages/getting-started-with-github-pages/what-is-github-pages);
it does not run this Python/KataGo service.

Work:

- Choose backend hardware and a spending limit after M2 benchmarks; get approval
  before provisioning paid infrastructure. Do not promise that free hosting is sufficient.
- Document binary/model/config setup, license/provenance, environment settings,
  readiness checks, startup, resource limits, logs and rollback.
- Keep private SGFs and player data out of normal logs and repository artifacts.
  Use unguessable job references, limited retention and basic abuse/rate controls.
- Verify upload limits, process cleanup, queue saturation and safe text rendering
  before enabling public access to expensive analysis.
- Establish a repeatable test-and-deploy process. Previous workflow pushes were
  rejected for missing token scope; inspect permissions before choosing Actions.
  Do not assume `main` pushes automatically update `gh-pages`.
- Update README with verified commands, actual backend/site URLs and known limits.

Release gate:

1. A fresh checkout can be installed and started from the documented instructions.
2. An uploaded supported SGF and equivalent manual game both complete real analysis.
3. A documented real-engine fixture with an obvious loss produces the expected
   mistake region within stated numeric tolerance; recommendations are traceable.
4. Clicking a listed mistake shows the correct position and both markers.
5. No mock values, invented PVs or unsupported Go diagnoses enter the release report.
6. Missing engine, invalid input, full queue and cancellation behave as documented.
7. Another device on a different network completes a review without relying on the
   developer's localhost. Record the deployed commit, engine/model, test inputs,
   benchmark results and known limitations before declaring v1 complete.

## Execution Rules

Work in milestone order; use small reviewed changes rather than one rewrite.
Each milestone closes with its acceptance evidence and an updated status document.
Keep the prototype available while replacements are built, but remove retired
runtime paths when their consumers migrate. Do not retain experiments as silent
fallbacks in the final default flow.

Next functional work: **M4's bounded analysis jobs and complete browser workflow**.
M2 is the first real-analysis milestone, M4 is the local usable web milestone, and
M5 is the first public usable release. No completion dates are committed before
the real-engine and deployment benchmarks.
