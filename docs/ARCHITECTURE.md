# Architecture

*Status: target design for the rebuild, written 2026-11-03 before any new code
exists. Items marked **Proposal (ADR-Pxx)** await the owner's decision in
[DECISIONS.md](DECISIONS.md). Nothing here describes shipped behavior.*

## 1. Overview

```text
                    ┌──────────────────────────────────────────────┐
  SGF files ───────►│ L0  Rules core (Rust: weiqi-core)            │◄── browser (WASM)
  manual entry      │     rules · sgf · zobrist · scoring          │
                    └───────────────┬──────────────────────────────┘
                                    │ PyO3 (weiqi_core)
                    ┌───────────────▼──────────────────────────────┐
                    │ L1  Engine adapter (Python asyncio)          │──► KataGo analysis engine
                    │     process · queries · cache · provenance   │    (JSON lines over stdio)
                    ├──────────────────────────────────────────────┤
                    │ L2  Metrics (single game)                    │
                    ├──────────────────────────────────────────────┤
                    │ L3  Diagnosis & profile (many games)         │
                    ├──────────────────────────────────────────────┤
                    │ L4  Explanation (facts → templates → text)   │
                    ├──────────────────────────────────────────────┤
                    │ L5  Training (exercises · scheduling)        │
                    ├──────────────────────────────────────────────┤
                    │ L6  API (FastAPI) + jobs + storage           │
                    └───────────────┬──────────────────────────────┘
                                    │ HTTP / SSE (JSON, versioned)
                    ┌───────────────▼──────────────────────────────┐
                    │ L7  Frontend (TypeScript · React · Vite)     │
                    └──────────────────────────────────────────────┘
```

Dependency rule: a layer may import only layers above it in this diagram
(lower number). Storage is a service used by L1–L6 through repository
interfaces; layers L2–L5 are pure functions over data and never touch the
database or the engine directly. This makes each layer testable with plain
fixtures.

## 2. Repository layout

```text
Cargo.toml                 Rust workspace (members: crates/*)
crates/
  weiqi-core/              Pure Rust library, no I/O, #![forbid(unsafe_code)]
    src/coord.rs           Points, board geometry, SGF/GTP coordinate conversion
    src/board.rs           Board, chains, captures, suicide, simple-ko point
    src/rules.rs           Rule components, named presets, komi
    src/game.rs            Turn order, superko, setup stones, replay modes, undo
    src/zobrist.rs         Position hashing
    src/scoring.rs         Area and territory scoring, SGF results
    src/sgf/               Decoding, parser, arena tree, writer, game extraction
    tests/  benches/       Integration tests, proptest, criterion benchmarks
    fuzz/                  cargo-fuzz targets (own workspace, nightly toolchain)
  weiqi-py/                PyO3 bindings, built by maturin → Python module `weiqi_core`
  weiqi-wasm/              wasm-bindgen bindings → JS/TS package for web/
python/
  pyproject.toml           uv project; distribution name = brand (see CLAUDE.md §6)
  src/weiqi/
    engine/                L1: KataGo process, query model, cache, provenance
    metrics/               L2
    profile/               L3
    explain/               L4 (+ locale catalogs, glossary)
    training/              L5
    storage/               SQL schema, migrations, repositories
    api/                   L6: FastAPI app, routes, jobs
    project.py             Reads config/project.json (brand lives there only)
  tests/
web/                       Vite + React + TypeScript
config/
  project.json             name, slug, tagline (the single runtime brand source)
  katago/*.cfg             Analysis configs (no weights)
testdata/
  sgf/                     Public SGF corpus with PROVENANCE.md
  conformance/             Golden cases and transcripts for Rust, Python and WASM
  engine/                  Recorded, sanitized KataGo responses with provenance
legacy/                    The prototype during transition (removed after M4)
docs/
```

Decision (ADR-P10, accepted 2026-11-03): one core crate with modules, plus two
thin binding crates, instead of separate `rules` and `sgf` crates. Fewer Cargo concepts for a Rust
learner; modules can be split into crates later without API change.

## 3. L0 — Rules core (Rust, `weiqi-core`)

The only implementation of Go rules in the project. Python and the browser
call it through bindings and never re-implement legality.

### 3.1 Board representation

- Boards are rectangular, `W × H` with `1 ≤ W, H ≤ 25` in the core. The engine
  layer restricts sizes to what the configured KataGo build reports.
- A point is a `u16` index into a flat array. Neighbors are precomputed once
  per board size, so the hot loop never does coordinate arithmetic.
- Stones: `Vec<Cell>` where `Cell` is `Empty | Black | White`.
- Chains and liberties start with **flood fill using a generation-stamped
  visited array** (no per-call allocation). It is simple to reason about and
  fast enough for review workloads. Incremental chain structures (as in KataGo)
  are only introduced if a criterion benchmark shows a need.

Rust note for the owner: the board owns its `Vec`s; functions borrow it
(`&Board` to read, `&mut Board` to play). No lifetimes appear in the public API
because callers receive owned values (`Vec<Point>`, `MoveEffect`), not
references into the board.

### 3.2 Moves, captures and ko

`Game::play_as(color, move, mode)` (and `play(move)` for the player to move)
returns `Result<MoveEffect, IllegalMove>`:

1. Reject occupied points.
2. Place the stone; remove adjacent opponent chains with zero liberties
   (captures).
3. If the new chain has zero liberties: suicide. Illegal unless the rule set
   allows multi-stone suicide (KataGo's `multiStoneSuicideLegal`, as in
   Tromp-Taylor and New Zealand), in which case the own chain is removed. A
   lone stone with no liberties is always illegal, as in KataGo.
4. Ko: simple ko is the point recorded when exactly one stone was captured by a
   single stone that ends with one liberty. Superko is checked with the
   position-hash history:
   - **positional superko**: the resulting stone arrangement must not repeat;
   - **situational superko**: arrangement plus side to move must not repeat;
   - **Japanese rules**: no superko; long cycles are allowed and recorded as
     a warning (a real game may end as "no result").

Validation has two modes:

- `Strict` for manual entry: illegal moves are rejected.
- `Record` for imported SGFs: the game is replayed as recorded; rule
  violations are reported as structured warnings with the move number, so a
  real-world record with a server-side quirk is still reviewable. Whether a
  flagged game may be analysed is a product policy decided in the API layer.

### 3.3 Rule sets

A `Rules` value mirrors KataGo's rule components so a query maps 1:1 onto the
engine: ko rule (`Simple`, `Positional`, `Situational`), scoring (`Area`,
`Territory`), suicide allowed, tax rule, button, white handicap bonus. Named
presets (`japanese`, `korean`, `chinese`, `chinese_superko`, `aga`,
`aga_button`, `new_zealand`, `tromp_taylor`, `stone_scoring`) are constructors
matching KataGo's rule names. `Komi` accepts finite half-point values in
−150…150. Handicap and setup stones (`AB`/`AW`/`AE`, `PL`) are part of the
initial position (`Setup`, `Game::with_setup`), not moves.

### 3.4 Zobrist hashing

Algorithm: assign a random key to each `(x, y, color)` on a 25×25 grid, one to
"white to move", one per simple-ko point, and one per width and height. A
position's hash is the XOR of the keys that apply to it. Because XOR is its own inverse, placing or removing
a stone updates the hash in O(1): `h ^= key[p][c]`.

- **Width: 128 bits** (proposal, ADR-P03). Hashes are stored in the database
  and compared across hundreds of thousands of games; 64-bit keys make a
  birthday collision unlikely but not negligible at that scale, while 128 bits
  cost almost nothing.
- **Determinism:** keys are generated from a fixed seed by a documented PRNG
  (SplitMix64), so Rust, Python and WASM produce identical hashes, and stored
  hashes stay valid. A `ZOBRIST_VERSION` constant is stored with every hash;
  changing keys requires a data migration.
- **Across the JS boundary** hashes are lowercase hex strings, because a
  JavaScript `number` cannot hold 64 or 128 bits exactly.
- Two hashes are exposed: `stones_hash` (arrangement and board size, for
  positional superko and cross-game lookup) and `situation_hash` (plus side to
  move and simple-ko point, for exact legality state).

Properties tested with proptest (`tests/properties.rs`) and fuzzed (`game`
target): after every random move sequence, in both replay modes, the
incremental hash equals the hash recomputed from scratch, rejected moves change
nothing, and undo restores every earlier position.

### 3.5 Scoring

- **Area (Chinese):** stones on board + empty regions bordered by only one
  color, after removing stones marked dead; komi applied.
- **Territory (Japanese):** surrounded empty points + prisoners + dead stones as
  prisoners; empty points in seki are not territory; komi applied.

Dead stones and seki cannot be decided by rules alone. The scorer takes a
`LifeAndDeath` input (dead chains and seki chains, each named by any one of
their stones). In the product this input is proposed from KataGo ownership and
confirmed or edited by the user; the scorer itself stays deterministic.

The entry point is `score(&Board, Captures, &LifeAndDeath, &Terms)`, where
`Terms` holds rules, komi, handicap and the button holder; `Game::score(&marks)`
fills these from a game. The board and captures are passed instead of a
`Position` so that the scorer does not depend on the game layer. Following
KataGo, White receives komi plus the handicap bonus, the button gives half a
point to the first player to pass, and under `TaxRule::Seki` empty points
bordering a seki chain belong to nobody. `TaxRule::All` is reported as
unsupported (`unsupported_rule`) rather than approximated. Results are
emitted in SGF `RE` format (`GameResult`).

### 3.6 SGF

Pipeline: **bytes → decode → parse to arena tree → extract game**.

- **Decoding** comes first, because GBK, Big5 and Shift_JIS trail bytes can
  equal `]` or `\`. Order: a BOM; else a declared `CA` (a Latin-1 declaration
  on non-ASCII bytes that are valid UTF-8 is overridden to UTF-8, with a
  warning); else the first strict decode among UTF-8, GB18030 (a superset of
  GBK), Big5, Shift_JIS and EUC-KR via `encoding_rs`; else lossy UTF-8. Every
  fallback is reported as a warning. Chinese server exports in GBK are a known
  real-world case.
- **Parser** is a single iterative pass (explicit stack, no recursion, no
  separate lexer), so deeply nested variation trees cannot overflow the stack.
  Errors and warnings carry byte offsets.
- **Arena tree:** `Vec<Node>` with `NodeId(u32)` parent/child indices. This avoids
  `Rc<RefCell<…>>` and borrow-checker friction, serialises trivially and is
  cache-friendly. Properties are kept raw (`Property { ident, values:
  Vec<Value> }`, each value the text between the brackets with its escapes), and
  typed accessors interpret them, so unknown properties round-trip unchanged.
- **Leniency** (each produces a warning, never silent): missing `FF`/`GM`,
  lowercase-prefixed FF[1–3] identifiers, `tt` as pass on boards ≤ 19, compressed
  point lists, whitespace and junk outside the tree, collections of multiple
  games (returned as a list), comments and markup kept.
- **Strictness:** limits on bytes, node count and depth (defaults 16 MiB,
  1,000,000 nodes, depth 10,000; `ParseLimits`); malformed coordinates or
  contradictory properties are errors with stable codes.
- **Extraction** (`extract(&SgfTree) -> GameRecord`) reads the main line only.
  Missing or invalid rules and komi become `None` plus a warning, never a
  default, so they must be confirmed before analysis (G04).
  `GameRecord::replay(rules, komi)` replays it in `Record` mode.
- **Writer:** canonical serialisation; `parse(write(t)) == t` is a proptest.
  Fuzz targets: `decode`; `parse` (parse, extract and replay); `round_trip`
  (parse, write, parse).

### 3.7 Public API shape

A small, owned API that binds cleanly to both Python and JS:

```text
Game::new(size, rules, komi)   Game::with_setup(size, rules, komi, setup)
game.play(mv) / game.play_as(color, mv, mode) -> Result<MoveEffect, IllegalMove>
game.undo() -> Option<(Color, Move)>
game.position() -> Position { size, cells, to_play, ko_ban, captures,
                              consecutive_passes, stones_hash, situation_hash }
game.replay(&moves, mode) -> Result<Replay { game, positions, warnings }, ReplayError>
game.score(&marks) / score(&board, captures, &marks, &terms) -> Result<Score, ScoreError>
sgf::parse(bytes) -> Result<Collection { games: Vec<SgfTree>, encoding, warnings }, SgfError>
sgf::extract(&tree) -> Result<GameRecord, ExtractError>   tree.to_sgf()
record.replay(rules, komi) -> Result<Replay, RecordReplayError>
```

As built in M1. There is no `Game::from_sgf`: parsing, extraction and replay
are separate steps, so that rules and komi can be confirmed between them.

## 4. Bindings

- **Python (`weiqi-py`, PyO3 + maturin).** Exposes the API above as Python classes
  with a hand-written `.pyi` stub checked by mypy. CPU-heavy calls such as batch
  SGF parsing release the GIL. Built in development with `maturin develop`
  through uv; wheels built in CI.
- **WASM (`weiqi-wasm`, wasm-bindgen).** Exposes a JS-friendly subset (create
  game, play, undo, snapshot, parse SGF, legal-move mask). TypeScript types are
  generated. Bundle size is measured and recorded, not promised in advance.
  Tooling choice (wasm-pack vs. the `wasm-bindgen` CLI directly) is decided in M2
  after checking current maintenance status.
- **Conformance:** one set of golden cases (JSON: input, expected positions,
  hashes, warnings) runs through Rust, Python and WASM in CI; any divergence fails.
  Cases and their hand-checked expectations are written by hand; the full
  transcripts are generated by the Rust runner, which refuses to write them
  if a hand check fails. Format: `testdata/conformance/README.md`.

## 5. L1 — Engine adapter (Python, asyncio)

Uses the KataGo **analysis engine** JSON-lines protocol
([official documentation](https://github.com/lightvector/KataGo/blob/master/docs/Analysis_Engine.md)).

### 5.1 Process

- One long-lived `katago analysis` process per configured engine, started with
  `asyncio.create_subprocess_exec`, kept warm across jobs (the prototype
  restarted it for every game).
- A reader task parses each stdout line and routes it by `id` (and
  `turnNumber`) to the waiting query's future or queue; stderr is drained and
  discarded by default so private paths are not logged.
- In-flight queries are bounded by a semaphore sized to the engine config.
- **Cancellation:** cancelling an asyncio task sends KataGo's `terminate`
  action for that query id and resolves the waiter as cancelled.
- **Timeouts:** per query and per job; on timeout the query is terminated.
- **Failure:** if the process exits, pending queries fail with
  `engine_unavailable`, and the supervisor restarts it with backoff.
- **Readiness:** `query_version` and `query_models` at start-up; the model file
  and config are SHA-256 hashed.

### 5.2 Queries

A frozen `AnalysisRequest` holds board size, rules, komi, initial stones,
initial player, moves, analysed turns, `maxVisits`, `analysisPVLen`, whether
ownership is included, and override settings. Whole games are sent as one query
with `analyzeTurns`, giving one response per turn. Raw values are always
requested in BLACK perspective (`reportAnalysisWinratesAs=BLACK`) and
normalised in one place.

Fields consumed: `rootInfo` (`scoreLead`, `winrate`, `visits`,
`currentPlayer`), `moveInfos` (`move`, `order`, `visits`, `scoreLead`,
`winrate`, `prior`, `pv`), and `ownership` when requested. Missing fields stay
`None`; non-finite values are protocol errors (as in the prototype).

### 5.3 Cache and reproducibility — Proposal (ADR-P03)

KataGo's neural-network input includes recent move history, and its search
uses that history for ko/superko. Two games reaching the same stones by
different orders can therefore produce slightly different outputs. So:

- **Cache key = `query_key`**: SHA-256 of the canonical JSON of the engine
  identity (version, model SHA-256, config SHA-256, overrides) plus the full
  request (rules, komi, size, initial stones, moves up to the analysed turn,
  visits, PV length, ownership flag). Same key → the stored result is reused
  exactly.
- **Zobrist `stones_hash` is an index, not the key**: it finds the same position
  across games (transpositions, repeated opening patterns, duplicate
  exercises). A result reached by hash only is labelled a transposition reuse.
- Each stored result records `query_key`, `stones_hash`, engine identity, visits,
  elapsed time and warnings. Re-running the same request reproduces the setup
  exactly; values agree within search noise, because multi-threaded search is
  not bit-for-bit deterministic.

The owner's brief specified "cache keyed by Zobrist hash". This proposal keeps
Zobrist hashing central but separates *exact reuse* from *position lookup* for
the reason above.

### 5.4 Recorded responses

A recording mode stores sanitized query/response pairs as test fixtures (only
public or synthetic games, no absolute paths), following the prototype's
`tests/fixtures/katago_real_short.json` approach. Replay tests use them for
deterministic coverage; live tests are opt-in.

## 6. L2 — Metrics (single game)

Pure functions from `(Replay, [PositionEvaluation])` to `GameMetrics`. All
values carry units, perspective and a definition id (e.g.
`score_loss.sequential.v1`).

### 6.1 Score loss — Proposal (ADR-P02)

Two definitions, both computable from the same evaluations:

- **Same-root** (the prototype's definition): in the search of the position
  before move *n*, `best.scoreLead − played.scoreLead` (mover's perspective).
  If the played move was not searched, an extra restricted search
  (`allowMoves`) is needed. Weakness: played moves often receive few visits,
  and the restricted search is a separate tree anyway; on the prototype's
  235-move benchmark this required 40 extra searches (docs/M2_ACCEPTANCE.md).
- **Sequential**: `root.scoreLead(before n) − root.scoreLead(after n)`, both in
  the mover's perspective. Every position is searched with the full budget
  anyway, so this costs no extra query, and the played move's value comes from
  a full search. Weakness: it compares two different searches, so it includes
  noise from both.

Proposal: make **sequential** the primary `score_loss`, keep **same-root** as a
recorded diagnostic and as the bridge for comparison tests against the
prototype. Both keep the prototype's conventions: `raw` retained, `score_loss =
max(0, raw)`, negative raw differences flagged as search noise. The owner
decides.

### 6.2 Other per-move metrics

- `winrate_delta_pp`: same structure as score loss, percentage points, mover's
  perspective. Never used alone for severity.
- **Ownership delta:** per point, `ownership(after) − ownership(before)`, mover's
  perspective.
- **Group status change:** for each chain (from the rules core) compute mean
  ownership; classify `alive` / `dead` / `unsettled` with versioned thresholds;
  emit a `GroupStatusChange` fact when the class changes between before and
  after the move, or between the played line and the best line's PV end.
- **Turning points:** moves where the mover's winrate or score crosses defined
  bands (e.g. from "winning" to "losing" territory) or that carry the largest
  share of a game's total loss. Defined numerically and versioned; the
  prototype's heuristics (winrate cliff, clustering radius) are a reference only.
- **Severity:** thresholds on `score_loss` from a calibration table selected by
  the player's strength band (pillar 4). Defaults remain product settings.

### 6.3 Phase and situation classification (v1)

Deterministic, multi-label, versioned detectors over facts. Each must be
evaluated against owner-labelled positions before its statistics are shown as
non-experimental.

| Label | Draft rule (to be calibrated) |
| --- | --- |
| Phase: opening / middle / endgame | From move number *and* the share of points with settled ownership (`|own| ≥ t`); the boundary values are calibrated, not assumed |
| Life and death | A chain of ≥ k stones changes status (6.2) after the move or along the best PV |
| Ko | The rules core detects a ko capture in the actual sequence or in the PV within m moves |
| Invasion / reduction | Move placed where the opponent's prior ownership ≥ t, with no friendly stone nearby |
| Endgame | Endgame phase, no group status change, local ownership change only |
| Other | None of the above |

## 7. L3 — Diagnosis and profile (many games)

- **Unit of analysis is the game**, because moves within a game are correlated.
  Per game: loss per move by phase and by situation label, mistake counts, loss
  share of turning points.
- **Confidence intervals:** cluster bootstrap over games (resample games, not
  moves); intervals shown with sample sizes; below a minimum sample size a cell
  is shown as "insufficient data". Proposal (ADR-P06).
- **Trends:** rolling windows by game date with the same interval method.
- **Comparability strata:** score loss depends on model and visits. Aggregates
  only combine analyses with the same metric definition and compatible engine
  settings; otherwise they are reported separately.
- Filters: color, time control, opponent strength, source, date range.

## 8. L4 — Explanation

**Facts → template → text.**

1. *Fact extraction* produces typed facts with all numbers and coordinates,
   e.g. `ScoreLoss{move, points}`, `BetterMove{move, pv}`,
   `GroupStatusChange{stones, from, to}`, `Phase{...}`, `Situation{...}`.
2. *Template selection* is deterministic and keyed by fact combinations and
   the player's strength band (what to emphasise).
3. *Rendering* fills locale templates (`zh-CN`, `en`) with terms from a
   glossary (e.g. 死活 / life and death, 劫 / ko, 打入 / invasion, 官子 /
   endgame), so terminology is consistent and reviewable.
4. *Optional LLM polishing (later):* input is the fact list only; output is
   rejected if it contains any coordinate, number or move sequence not present
   in the facts. The template text is always available as the fallback.

## 9. L5 — Training

- **Exercise generation:** a position before a significant mistake becomes an
  exercise. It is re-analysed with a higher visit budget; acceptable answers
  are the moves whose loss relative to the best is within a tolerance chosen by
  strength band. Duplicates across games are merged via `stones_hash`.
- **Answer checking:** an answer in the precomputed set is graded immediately;
  any other legal answer is evaluated by the engine before it is graded. No
  grade is guessed.
- **Scheduling:** a spaced-repetition algorithm; proposal FSRS (ADR-P05), with
  every review logged so the schedule can be recomputed.
- **Re-measurement:** each exercise links to a weakness category; the profile
  tracks that category's frequency and loss in games played after practice
  began, with the same interval method as L3. Correlation is not presented as
  causation.

## 10. L6 — API, jobs and storage

### 10.1 API

FastAPI with Pydantic models; OpenAPI is the contract, and TypeScript types are
generated from it. Progress is pushed with Server-Sent Events, with polling as
a fallback. Resource groups (to be detailed per milestone): games (upload,
list, metadata confirmation), analyses (start, progress, cancel, result),
profile, exercises (due list, answer), settings (strength band, thresholds).

### 10.2 Jobs

Persistent job rows plus an in-process asyncio worker on a single node. The
prototype's guarantees are kept: bounded queue, stable input snapshot per job,
cancellation that releases engine work, explicit states (`queued`, `running`,
`succeeded`, `failed`, `cancelled`), progress that never pretends a partial
result is complete. The worker interface allows moving to a separate process
later without changing the API.

### 10.3 Storage

SQLite first; the schema is written for PostgreSQL portability:

- SQLAlchemy Core with Alembic migrations (proposal ADR-P08); no
  SQLite-only features; text UUIDs; UTC timestamps; JSON in `TEXT` columns
  that map to `JSONB` later; large numeric arrays (ownership) as compressed
  BLOB/`bytea`.
- Migrations are tested against both SQLite and PostgreSQL in CI once the
  schema exists (from M3).

Draft entities: `player`, `game` (source, SGF bytes hash, metadata, rules),
`analysis_run` (engine identity, settings), `position_eval` (`query_key`,
`stones_hash`, turn, root values, candidates JSON, ownership blob), `move_metric`
(definition id, values), `label` (classifier and owner gold labels), `exercise`,
`review_log`, `job`.

## 11. L7 — Frontend

- **Stack:** TypeScript, React, Vite. Server state via a query cache library
  (TanStack Query, decide in M2); local UI state kept minimal.
- **Board:** SVG rendering (crisp at any size, styleable, testable DOM);
  legality, captures and ko through the WASM core, so manual entry needs no
  server round-trip per stone (the prototype calls the server for every click).
- **Visualisation:** a clickable loss timeline that jumps to positions; an
  interactive profile (phase × situation grid with intervals, trends). Library
  choice (D3 modules rendered by React, or a higher-level library) decided in M4.
- **Design:** restrained palette, generous whitespace, strict alignment grid;
  Baskerville-family serif for Latin display text and a matching CJK serif for
  Chinese headings, sans-serif body text; fonts self-hosted under open licences
  after licence review.
- **Language:** `zh-CN` and `en` catalogs; numbers and Go terms from the same
  glossary as L4.

## 12. Cross-cutting concerns

- **Configuration:** typed settings from environment and `config/`; brand only
  in `config/project.json`; no brand-prefixed environment variables.
- **Errors:** stable codes across Rust, Python and API (`invalid_sgf`,
  `illegal_move`, `engine_unavailable`, ...).
- **Logging:** structured; never logs SGF content, player names or absolute paths
  by default.
- **Security and privacy:** upload size limits, safe text rendering, no private
  data in fixtures. The prototype's public-mode protections (host checks, rate
  limits, retention) are the reference for M8.
- **Versioning:** result schemas, metric definitions, classifier versions and
  Zobrist version are separate version numbers from the product version.

## 13. Layer-by-layer comparison with the prototype

Prototype paths refer to the repository before M0 (they move to `legacy/` in M0).

| Layer | Prototype (verified by reading the code, 2026-11-03) | Rebuild |
| --- | --- | --- |
| L0 Rules | `src/game.py` replays with sgfmill's `Board`; app code adds turn order, suicide, simple ko. No superko, no scoring, no hashing, no setup stones or handicap (rejected), 19×19 only | Rust core with rule sets, superko, scoring, Zobrist, setup/handicap, sizes up to 25 |
| L0 SGF | `src/sgf_parser.py` on sgfmill: UTF-8 only, first variation only, rejects `AB/AW/AE/PL/KO`, `HA≠0`, multi-game files, `tt` pass | Own parser: full variation tree, encodings, leniency with warnings, fuzzed |
| Browser rules | None: every click POSTs the full game to `/api/v1/replay-moves` (`frontend/input-state.mjs`) | WASM core in the browser; server re-validates on submit |
| L1 Engine | `src/katago_client.py`, `src/katago_process.py`: synchronous selectors loop, one process per game, 16-turn batches, ID/turn matching, forced played-move search, provenance; POSIX only | asyncio, long-lived process, terminate-based cancel, cache, recorded fixtures; same strict parsing rules |
| L2 Metrics | `src/mistake_selector.py`, `src/mistake_severity.py`: same-root score loss, winrate delta in pp, fixed 3/5-point thresholds, top-5 cap via `limit` 1–5 | Sequential + same-root (proposal), ownership, group status, turning points, strength-dependent thresholds |
| L3 Profile | None (no persistence, no multi-game) | New |
| L4 Explanation | `src/report_writer.py`: Chinese factual one-line templates; heuristic teaching retired in M3 (`classifier.py`, `key_points.py` in history) | Fact model + bilingual templates + glossary |
| L5 Training | None | New |
| L6 API/jobs | `app/main.py`, `app/jobs.py`: FastAPI, one worker thread, in-memory jobs with retention, polling; `app/public.py` rate limits | FastAPI, persistent jobs, SSE, SQLite storage |
| L7 Frontend | `frontend/*.mjs`: vanilla JS, Canvas board, 962-line `review-controller.mjs`, Node unit tests | React + TypeScript + Vite, SVG board, Vitest + Playwright |
| Results | `src/review_result.py`: schema 3.0 dataclasses with Chinese strings embedded (`"未知"`, severity labels, method note) | Results carry codes and numbers only; rendering is localised |
| Tooling | setuptools, top-level packages named `src` and `app`, pinned constraints, no CI, no lint/type config, no LICENSE file | uv, cargo, npm; ruff, mypy, clippy, eslint; GitHub Actions |
