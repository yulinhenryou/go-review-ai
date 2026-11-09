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
  weiqi-wasm/              wasm-bindgen bindings → JS/TS module in web/src/wasm/ (generated)
python/
  pyproject.toml           uv project; distribution name = brand (see CLAUDE.md §6)
  src/weiqi/
    engine/                L1: KataGo process, query model, cache, provenance
    metrics/               L2: per-move loss, severity, mistake selection
    profile/               L3
    explain/               L4 (+ locale catalogs, glossary)
    training/              L5
    storage/               SQL schema, migrations, repositories
    api/                   L6: FastAPI app, routes, jobs
    tools/                 Developer tools: fixture recording, benchmarks
    project.py             Reads config/project.json (brand lives there only)
  tests/                   Unit and replay tests; tests/live/ is opt-in real KataGo
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
game.chains() -> Vec<Chain { color, stones, liberties }>   (M4)
game.replay(&moves, mode) -> Result<Replay { game, positions, warnings }, ReplayError>
game.score(&marks) / score(&board, captures, &marks, &terms) -> Result<Score, ScoreError>
sgf::parse(bytes) -> Result<Collection { games: Vec<SgfTree>, encoding, warnings }, SgfError>
sgf::extract(&tree) -> Result<GameRecord, ExtractError>   tree.to_sgf()
record.replay(rules, komi) -> Result<Replay, RecordReplayError>
```

As built in M1. There is no `Game::from_sgf`: parsing, extraction and replay
are separate steps, so that rules and komi can be confirmed between them.

## 4. Bindings

- **Python (`weiqi-py`, PyO3 + maturin).** Exposes the API above, except
  scoring for now, plus GTP vertex conversion (`to_gtp`, `from_gtp`) for the
  engine adapter, as the module `weiqi_core` with a hand-written `.pyi` stub
  that `mypy.stubtest` checks against the built module (ADR-P15). `python/`
  depends on it as a uv path source, so `uv sync` builds a wheel with maturin
  and installs it; CI runs the Python tests against that wheel. `parse_sgf`
  releases the GIL while it parses. Ownership at the boundary:
  - `Game` owns its Rust `Game` inside the Python object. Rust's compile-time
    borrow rules cannot see Python references, so PyO3 tracks borrows at run
    time: a method taking `&mut self` (`play`, `undo`) raises instead of
    running while another borrow of the same object is active.
  - Every other class is `frozen` and owns a copy: `Position`, `MoveEffect`
    and the warning classes copy their values out of the core; `SgfTree` and
    `GameRecord` own the core's tree and record, moved in, and build new
    Python lists on each attribute access. Nothing Python holds borrows from
    Rust, so no Rust lifetime crosses the boundary.
  - `parse_sgf` borrows the immutable `bytes` argument for the duration of
    the call instead of copying it.
- **WASM (`weiqi-wasm`, wasm-bindgen).** Exposes a JS-friendly subset: a
  `Game` class (create, with setup, play, undo, snapshot) and two pure SGF
  functions, `parseSgf` and `replaySgf` (ADR-P16). Built with the
  `wasm-bindgen` CLI directly (`--target web`), pinned to the crate's exact
  version 0.2.130, by `npm run wasm` in `web/`, which writes the generated
  module to `web/src/wasm/` (not committed). The TypeScript types come from
  wasm-bindgen: interfaces in a `typescript_custom_section` and
  `unchecked_param_type`/`unchecked_return_type` on each export. Size is
  measured, not promised (M2 acceptance record). A legal-move mask is not
  built yet. Ownership at the boundary:
  - `Game` is a handle: its Rust `Game` lives in WASM linear memory and JS
    holds an index to it, so it must be released with `free()` or `using`.
    wasm-bindgen checks borrows at run time, as PyO3 does.
  - Everything else is a plain JS object or array, copied out of WASM memory
    through serde DTOs (`serde-wasm-bindgen`), so it needs no `free()` and
    can be kept in UI state. Hashes are hex strings.
  - `parseSgf`/`replaySgf` take bytes that wasm-bindgen copies into WASM
    memory for the call. `replaySgf` parses again rather than keeping a
    handle between the two calls.
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
  `engine_unavailable`, and the supervisor (`KataGoEngine`) starts a new
  process on the next call, waiting with exponential backoff after failed
  starts. Restarting lazily keeps one code path for start-up errors, which
  reach the caller instead of a background task. Any
  protocol violation (malformed JSON, an unknown id or turn, a missing
  final-result marker, a duplicate reply, a line over 4 MiB) fails every
  pending query with `EngineProtocolError` and stops the process, since the
  stream can no longer be trusted. An engine `error` fails only its query;
  a `warning` about `rules`, `komi` or `overrideSettings` fails and
  terminates its query, and other warnings are kept with the replies.
- **Working directory:** each process runs in an empty temporary
  directory, removed on close, so the engine never writes into the
  repository.
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

A restricted search (M4, MIGRATION E04) is a request with `allow_move` set:
one analysed turn, no ownership, and `allowMoves` limiting the root's first
move to the move played there (`untilDepth` 1), so the played move gets the
whole budget when the free search gave it no value. The restriction is part
of the search fields and therefore of `query_key`; free searches send no
`allowMoves` and keep their keys. `weiqi.metrics.played_moves_to_search`
chooses the turns (the played move missing from the candidates, or without a
score lead or visits, as in the prototype), and `weiqi.review` sends them
together through the cached analyzer.

### 5.3 Cache and reproducibility (ADR-P03)

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

The owner's brief specified "cache keyed by Zobrist hash". ADR-P03 keeps
Zobrist hashing central but separates *exact reuse* from *position lookup* for
the reason above.

Implemented in M3 step 5: `CachedAnalyzer` (`weiqi/engine/cached.py`) asks
the engine for its identity, computes every requested turn's `query_key`,
loads the stored ones from a `ResultStore`, sends only the missing turns as
one query, and stores the answer when the query completes (a cancelled or
failed query stores nothing). It counts hits and misses. The engine layer
defines the `ResultStore` interface; `weiqi/storage/results.py` implements
it in SQL (§10.3), so the engine layer never imports the database.
`AnalysisRequest.hashes` gives each turn's `stones_hash` and
`situation_hash` from the core's replay.

### 5.4 Recorded responses

`EngineProcess` and `KataGoEngine` accept an optional transcript callback
that sees every message sent and every JSON object received, in order,
including replies the process ignores. `python -m weiqi.tools.record_engine`
uses it to store one real exchange as a fixture in `testdata/engine/`,
following the prototype's `tests/fixtures/katago_real_short.json`:

- Only records in `testdata/sgf/` that `PROVENANCE.md` lists can be recorded,
  so private games never become fixtures.
- Query ids are renumbered (`id-1`, ...), the loaded model's `name` is reduced
  to its file name, and the recorder refuses to write a fixture that still
  contains a local path.
- The fixture stores the input, the recording machine, the engine identity,
  the exchange, and each turn's normalised result and `query_key`.

Replay tests check that today's code sends the recorded query and turns the
recorded replies into exactly the recorded results, both through the parser
alone and through the whole client with the fake engine playing the
exchange back. Live tests in `python/tests/live/` run against the real
engine only with `RUN_KATAGO_INTEGRATION=1`.

## 6. L2 — Metrics (single game)

Pure functions from `(Replay, [PositionEvaluation])` to `GameMetrics`. All
values carry units, perspective and a definition id (e.g.
`score_loss.sequential.v1`).

### 6.1 Score loss (ADR-P02)

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

Decision: **sequential** is the primary `score_loss`, **same-root** is a
recorded diagnostic and as the bridge for comparison tests against the
prototype. Both keep the prototype's conventions: `raw` retained, `score_loss =
max(0, raw)`, negative raw differences flagged as search noise. Accepted by
the owner on 2026-11-09.

### 6.2 Other per-move metrics

- `winrate_delta_pp`: same structure as score loss, percentage points, mover's
  perspective. Never used alone for severity.
- **Ownership delta:** per point, `ownership(after) − ownership(before)`, mover's
  perspective.
- **Group status change** (`group_status.v1`, M4): for each chain on the board
  before the move (from the rules core, `Game.chains()`), the mean ownership
  of its stones in its own color's perspective is classified `alive` (≥ 0.6),
  `dead` (≤ −0.6) or `unsettled`, once with the ownership before the move and
  once after, on the same stones; a `GroupStatusChange` is emitted when the
  class changes or the move captures the chain. The thresholds are
  uncalibrated settings until owner-labelled positions exist. On the first
  real run (the 235-move game at 32 visits, one run) all 178 changes were of
  chains of one to three stones, many of them alternating between `alive`
  and `unsettled`; these are facts about the engine's view, and filtering by
  chain size belongs to the classifiers of §6.3. The comparison
  between the played line and the best line's PV end needs a search of the PV
  end position and is not built yet.
- **Turning points** (`turning_points.v1`, M4): Black's root winrate falls into
  three bands (Black ahead ≥ 0.7, White ahead ≤ 0.3, close between); a move is
  a turning point when the band after it is worse for the mover than the band
  before and the mover's winrate fell by at least 10 percentage points in
  that move (without this, a winrate hovering near a limit made turning points
  of moves that changed it by 1 to 9 points on the 235-move game at 32
  visits). Each one carries its share of the mover's total primary loss. The
  limits are uncalibrated settings; the prototype's heuristics (winrate cliff,
  clustering radius) were a reference only.
- **Severity:** thresholds on `score_loss` from a calibration table selected by
  the player's strength band (pillar 4). Until M5 the table has one default
  band: 4.0 points mistake, 8.0 severe (ADR-P17). Defaults remain product
  settings.

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

### 6.4 Review result (`review.v1`, M4)

`weiqi.review` turns one SGF game into one result document. It sits above
the engine and metrics layers and is the only part of a review that talks to
the engine:

1. **Input** (`read_game`, `confirm`): exactly one game per file; rules and
   komi are the caller's, else the record's when `RU` names a known rule set
   and `KM` is present; anything missing raises `metadata_unconfirmed` with
   the field (ADR-010). Replaying the record in the rules core rejects
   impossible moves before the engine is asked anything, and a record whose
   move breaks the selected rules (ko, superko, suicide, out of turn) or a
   game without moves is refused with the code and move number (ADR-P19).
2. **Evidence** (`review_game`): one whole-game query with ownership, then
   the restricted searches of played moves (§5.2), all through the cached
   analyzer, so a repeated review asks the engine nothing.
3. **Result** (`build_result`): codes and numbers only, no sentences, as
   canonical JSON (sorted keys, no NaN). It holds the game metadata (with
   `record_status`), engine provenance, a `method` block (metric
   definitions, perspectives, thresholds, `thresholds_calibrated: false`),
   coverage (moves with score, winrate and ownership evidence, the numbers
   of the moves without, whether the final position was evaluated), the
   chronological timeline with Black-perspective chart values, the ranked
   mistakes, turning points, the final position's candidates, and warning
   codes. The result is `partial` when any of that evidence is missing; a
   partial result never reads as "no mistakes". `warnings` concern the
   primary evidence; `diagnostic_warnings` hold the same-root flags, which
   concern only the diagnostic values (without played-move searches every
   same-root value is missing while the primary evidence is complete).

`weiqi.explain` renders a result as a plain-text report in `zh-CN` or `en`
(§8), and `python -m weiqi.review` runs all of this from the command line and
stores the run (§10.3).

First real run (2026-11-09, one run each, the owner's Apple M4, KataGo 1.18.2,
b18 model, 200 visits, `python -m weiqi.review` with an empty SQLite
database): the 235-move game needed 236 turns plus 25 played-move searches and
took 5 min 29 s; the same command again took 1.5 s, all 261 turns from the
cache. The result was complete; its largest sequential loss was 3.5 points
(move 8), so no move reached the default 4-point line, and 104 moves carried
the search-noise flag. On the synthetic `m3-mistake.sgf` the three first-line
Black moves were the three mistakes found (12.5, 11.9 and 8.9 points).

The comparison with the prototype (ROADMAP M4) passed on 2026-11-09: the
same-root diagnostic agrees with the prototype's loss within the
prototype's own run-to-run noise, and both refuse the same inputs except
nine the new review supports and the prototype did not. Data, method and
results: `testdata/comparison/README.md`; the checks re-run from the
recorded files in `python/tests/test_compare_legacy.py`.

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

M4 builds the catalog part: `weiqi/explain/locales/zh-CN.json` and `en.json`
map codes (colours, rule sets, severities, group statuses, winrate bands,
flags, input warnings) and report templates to text. Both have exactly the
same keys and placeholders (tested); a code without its own entry is shown
through a fallback entry that names the code, never dropped. The plain-text
report (`render_report`) only rewords and reorders what the result holds.
Fact-combination templates and the glossary come with the classifiers.

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

- SQLAlchemy Core with Alembic migrations (ADR-P08); no
  SQLite-only features; text UUIDs; UTC timestamps; JSON in `TEXT` columns
  that map to `JSONB` later; large numeric arrays (ownership) as compressed
  BLOB/`bytea`.
- Migrations are tested against both SQLite and PostgreSQL in CI once the
  schema exists (from M3): the CI `python` job starts a PostgreSQL service
  container and sets `TEST_POSTGRESQL_URL`; locally the storage tests run on
  SQLite only.
- SQLAlchemy runs synchronously; repositories offer async methods that run
  each call in a worker thread (`asyncio.to_thread`), so the event loop never
  waits on the database and no async database drivers are needed.
- The schema lives in `weiqi/storage/schema.py`; migrations in
  `weiqi/storage/migrations/` are applied with
  `python -m weiqi.storage.migrate upgrade <url>`. A test compares the
  migrated database with the schema module, so the two cannot drift.

M3 tables (the analysis cache):

- `engine_identity`: version, model name and SHA-256, config SHA-256,
  overrides; keyed by a hash of all of them.
- `engine_query`: one engine query: its identity, turn count and elapsed time.
- `position_eval`: one analysed turn, keyed by `query_key`: the producing
  query, turn, `stones_hash` (indexed) and `situation_hash` as 32-digit hex,
  player to move, visits asked, root visits, winrate and score lead (BLACK),
  candidates as JSON, ownership as zlib-compressed little-endian float64,
  engine warnings, and an encoding version. Every number round-trips exactly.
  When two queries store the same key, the first result is kept. Migration
  0002 (M4) adds `allow_move`, the move a restricted search was limited to
  (GTP vertex or "pass", `NULL` for a free search); the position index lists
  free searches only.

M4 tables (migration 0003, the reviews):

- `game`: one SGF file as uploaded (bytes), a text id, unique by SHA-256, so
  the same file is stored once however often it is reviewed.
- `review_run`: one review of a game: engine identity, confirmed rules and
  komi, the review settings as JSON, schema version, status and the whole
  result document, exactly as `ReviewResult.to_json` wrote it.
- `move_metric`: two rows per move of a run, one per score-loss definition
  (raw and clamped loss, winrate change, flags; severity for the primary
  definition only), indexed by definition and severity. It is written from
  the same result in the same transaction, so it never disagrees with the
  document; profiles (M5) aggregate it in SQL.

Draft entities for later milestones: `player`, `label` (classifier and owner
gold labels), `exercise`, `review_log`, `job`.

## 11. L7 — Frontend

- **Stack:** TypeScript, React, Vite. Server state via a query cache library;
  local UI state kept minimal. M2 has no server calls, so the choice of
  library (TanStack Query is the candidate) moves to the milestone that adds
  the first API call.
- **Core handles (M2):** components never hold a WASM handle in React state
  directly. A plain TypeScript session object (`web/src/session/`) owns the
  `Game` handle, returns plain snapshots, and frees the handle when a new game
  replaces it; React state stores those snapshots.
- **Board:** SVG rendering (crisp at any size, styleable, testable DOM);
  legality, captures and ko through the WASM core, so manual entry needs no
  server round-trip per stone (the prototype calls the server for every click).
  The M2 board has no coordinate labels and is operated by pointer only;
  labels and keyboard play on the board are open items for M4.
- **Visualisation:** a clickable loss timeline that jumps to positions; an
  interactive profile (phase × situation grid with intervals, trends). The M4
  timeline is React SVG without a chart library (ADR-P18); the profile charts
  revisit the choice in M5.
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
