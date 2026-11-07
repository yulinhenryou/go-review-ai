# Architecture Decision Records

*Started 2026-11-03. Fupan is a provisional name.*

Each record states context, decision and consequences. Status values:

- **Accepted (inherited)** — validated in the prototype and carried forward.
- **Accepted** — set by the owner's rebuild brief of 2026-11-03.
- **Proposed** — recommended by the planning session; the owner decides.
  Records marked *M0* must be decided before M0 starts.

Superseding a record means adding a new one that references it; records are
not edited after acceptance except for status.

## Inherited from the prototype

### ADR-001 Score loss in points is the primary mistake metric
- **Status:** Accepted (inherited). Definition refined by ADR-P02.
- **Context:** Winrate saturates near won or lost positions; point estimates
  (`scoreLead`) stay informative throughout the game.
- **Decision:** `score_loss` (points, mover's perspective) drives mistake
  detection, severity and ranking. Only `scoreLead` counts as points; utility
  is never used as a score.
- **Consequences:** Results show points first; aggregates sum and average points.

### ADR-002 Keep winrate delta as a secondary signal
- **Status:** Accepted (inherited).
- **Decision:** Record `winrate_delta_pp` in percentage points from the mover's
  perspective. It is displayed and used for turning points, but never alone
  determines severity.

### ADR-003 Identify meaningful turning points
- **Status:** Accepted (inherited); redefinition required.
- **Context:** The prototype's `key_points.py` used heuristic winrate-cliff rules;
  it was retired in its M3 together with unsupported teaching prose.
- **Decision:** Turning points remain a product concept, redefined numerically
  from engine evaluations, versioned, and tested (ARCHITECTURE §6.2).

### ADR-004 No artificial cap such as "top three"
- **Status:** Accepted (inherited).
- **Decision:** A ranked summary (default up to 5, configurable) plus the full
  chronological list of qualifying moves. Ranking: unrounded loss descending,
  then move number. Never pad the list.

### ADR-005 Versioned JSON output stays available
- **Status:** Accepted (inherited).
- **Decision:** Every result is available as versioned JSON for debugging and
  testing. Schema versions are independent of product versions.

### ADR-006 Native-language explanations for East Asian users
- **Status:** Accepted (inherited), extended to bilingual by ADR-021.

### ADR-007 Real engine only; no mock fallback in production
- **Status:** Accepted (inherited from prototype M2).
- **Decision:** If KataGo is unavailable the product reports an error. Mock
  engines exist only in tests and are labelled as such.

### ADR-008 Record provenance for every analysis
- **Status:** Accepted (inherited), extended by ADR-P03.
- **Decision:** Engine version, model id and SHA-256, config SHA-256, visits,
  rules, komi, perspective, request id, turn, warnings; no absolute local paths.

### ADR-009 Missing evidence stays missing; negative differences are noise
- **Status:** Accepted (inherited).
- **Decision:** Missing values remain null and reports show partial coverage
  explicitly. Raw differences are retained; `score_loss = max(0, raw)`; negative
  raw values are flagged as possible search noise, never presented as good moves.

### ADR-010 Rules and komi are explicit
- **Status:** Accepted (inherited).
- **Decision:** No hidden engine defaults. Missing rules or komi require user
  confirmation before analysis.

### ADR-011 Thresholds are product settings, not Go truths
- **Status:** Accepted (inherited).
- **Decision:** Defaults (3.0 points mistake, 5.0 severe) are a starting point for
  calibration and are presented as adjustable settings.

## Set by the rebuild brief

### ADR-012 Rust core is the single rules authority
- **Status:** Accepted.
- **Decision:** Rules, SGF and Zobrist hashing live in Rust (`weiqi-core`),
  exposed to Python via PyO3 + maturin and to the browser via wasm-bindgen.
- **Consequences:** A conformance suite must prove Rust, Python and WASM agree.
  Rust teaching is part of the work (CLAUDE.md §2).

### ADR-013 Python analysis and service layer
- **Status:** Accepted.
- **Decision:** asyncio KataGo analysis-engine adapter with batching, caching,
  timeouts and cancellation; metrics, profile and scheduling in Python; FastAPI.

### ADR-014 TypeScript, React and Vite frontend
- **Status:** Accepted.
- **Decision:** Board legality in the browser uses the WASM core.

### ADR-015 SQLite first, PostgreSQL-portable schema
- **Status:** Accepted. Access layer: ADR-P08.

### ADR-016 Monorepo and tooling
- **Status:** Accepted.
- **Decision:** Separate directories for Rust crates, the Python project and the
  web app; uv for Python; GitHub Actions running tests and `cargo clippy`,
  `cargo fmt`, `ruff`, `mypy`, `eslint`.

### ADR-017 Layering
- **Status:** Accepted.
- **Decision:** Rules core → engine adapter → metrics → diagnosis & profile →
  explanation → training → API → frontend, each independently testable.

### ADR-018 Migration through a tag and a `legacy/` directory
- **Status:** Accepted (details in MIGRATION.md).
- **Decision:** Tag the prototype, move it to `legacy/`, keep it runnable, build
  the new tree at the root, delete `legacy/` after the comparison tests pass.
  Conventional Commits. Full history preserved.

### ADR-019 Provisional name with centralised naming
- **Status:** Accepted.
- **Decision:** "Fupan" is provisional; the brand appears only in the locations
  listed in CLAUDE.md §6; internal identifiers are named by function.

### ADR-020 Non-goals
- **Status:** Accepted.
- **Decision:** No playing engine, no neural-network training, no competition on
  board editing with Sabaki or KaTrain.

### ADR-021 Explanations are deterministic; LLMs may only rephrase facts
- **Status:** Accepted.
- **Decision:** Bilingual (`zh-CN`, `en`) template explanations from structured
  facts. A future LLM layer receives only facts, and output introducing any
  coordinate, number or variation absent from the facts is rejected.

### ADR-022 Data sources
- **Status:** Accepted.
- **Decision:** Local SGF upload first. Online platforms later, only through
  means permitted by their terms, preferring public APIs.

### ADR-023 Toolchain versions and web tooling
- **Status:** Accepted 2026-11-03 under the owner's delegation during M0.
- **Decision:** Rust 1.99.1, edition 2024 (`rust-toolchain.toml`); Python 3.14
  (`python/.python-version`), one release behind the newest 3.15 for mature
  binding support (PyO3 0.30); Node ≥ 22.12, CI on Node 24; npm rather than pnpm
  (already installed, a single web package needs no workspace tool); eslint with
  typescript-eslint as the brief specified, not oxlint, which the current Vite
  template defaults to; TypeScript pinned to 6.0.3 because typescript-eslint
  8.72 supports only TypeScript < 6.1.
- **Consequences:** Upgrade TypeScript to 7 when typescript-eslint supports it,
  in its own PR. Version bumps are deliberate PRs, not side effects.

## Proposed by the planning session

### ADR-P01 Stable internal namespace `weiqi` *(M0)*
- **Status:** Accepted by the owner, 2026-11-03.
- **Context:** Internal names must not carry the brand, yet Python and npm need
  an import root. A Go-language name such as `go` invites the Golang confusion
  that ruled out "GoMind", and `core` collides with Rust's built-in `core` crate.
- **Decision:** Rust crates `weiqi-core`, `weiqi-py` (Python module
  `weiqi_core`), `weiqi-wasm`; Python import package `weiqi`; the brand appears
  only as the Python distribution name, the web `package.json` name and
  `config/project.json`.
- **Alternatives:** brand as import root (simpler, but every rename touches all
  imports); `goban` for the core crate (accurate for the board, less so for the
  analysis packages).
- **Consequences:** A rename edits only the checklist in CLAUDE.md §6.

### ADR-P02 Score-loss definition: sequential primary, same-root diagnostic *(before M4)*
- **Status:** Proposed.
- **Context:** The prototype compares best and played candidates inside the
  pre-move search (same-root). Played moves often receive few visits, and when
  absent they need a separate restricted search (40 extra searches on the
  235-move benchmark, per the prototype's M2 record). Every position is searched
  anyway, so the sequential difference of root values is available at no cost.
- **Decision:** Primary `score_loss` = root `scoreLead` before the move minus
  root `scoreLead` after it, both from the mover's perspective
  (`score_loss.sequential.v1`). Same-root is still computed and stored
  (`score_loss.same_root.v1`) as a diagnostic and for comparison with legacy.
- **Alternatives:** keep same-root as primary (continuity, single-tree
  comparison); report both without choosing.
- **Consequences:** Severity, ranking and profile use the sequential value; the
  M4 comparison uses the same-root value to compare with legacy fairly.

### ADR-P03 Cache key is the canonical query hash; Zobrist is a position index *(before M3)*
- **Status:** Proposed. Amends the brief's "cache keyed by Zobrist hash".
- **Context:** KataGo's network input includes recent move history, and ko and
  superko depend on history, so equal stone arrangements reached by different
  orders can be analysed differently.
- **Decision:** Exact reuse is keyed by `query_key` (SHA-256 of engine identity +
  full canonical request). A 128-bit deterministic Zobrist `stones_hash` (and a
  `situation_hash`) indexes positions across games for transpositions and
  exercise deduplication; reuse through it is labelled as such.
- **Consequences:** Reproducibility claims stay exact; cross-game position
  features keep their speed.

### ADR-P04 Roadmap adjustments *(M0)*
- **Status:** Accepted by the owner, 2026-11-03.
- **Decision:** Web shell in M2, single-game web review page in M4 (needed for
  legacy parity), storage foundation in M3, owner labelling sessions in M4–M5;
  M8 becomes design polish, deployment and public release.
- **Context:** Without these, deleting `legacy/` in M4 would remove the only web
  interface, WASM would go untested in a browser until M8, and the cache would
  have no storage.

### ADR-P05 FSRS for spaced repetition *(before M7)*
- **Status:** Proposed.
- **Context:** FSRS is an open, actively maintained scheduler with a published
  reference implementation in Python; SM-2 is simpler but older.
- **Decision:** Use FSRS through its reference Python library if its licence and
  maintenance check out at M7; log every review so schedules can be recomputed.

### ADR-P06 Game-level cluster bootstrap for intervals *(before M5)*
- **Status:** Proposed.
- **Context:** Moves within a game are correlated; treating moves as independent
  makes intervals too narrow.
- **Decision:** Resample games, not moves; show sample sizes; suppress cells
  below a minimum size; aggregate only comparable analyses (same metric
  definition and compatible engine settings).

### ADR-P07 Investigate KataGo's human-like model for strength calibration *(spike before M5)*
- **Status:** Proposed (investigation only).
- **Context:** KataGo releases since 1.15 document a "human SL" network with
  rank-conditioned profiles; the local KataGo 1.16.4 already reports a
  `usesHumanSLProfile` field in `query_models` (seen in
  `tests/fixtures/katago_real_short.json`). A rank-conditioned human policy could
  indicate how likely a player at a given level is to find a move, which fits
  pillar 4.
- **Decision:** Run a spike that verifies the exact analysis-engine fields and
  licence of the human model before any design depends on it. Nothing is
  promised until the spike is recorded.

### ADR-P08 SQLAlchemy Core and Alembic for storage *(before M3)*
- **Status:** Proposed.
- **Decision:** SQL expressed through SQLAlchemy Core (not a heavy ORM), schema
  migrations through Alembic, tested on SQLite and PostgreSQL in CI.

### ADR-P09 Repository licence *(M0)*
- **Status:** Accepted by the owner, 2026-11-03: **Apache-2.0**. The LICENSE
  file is added in M0. The KataGo network licence remains separate and applies
  only to the model.
- **Context:** The public repository has no LICENSE file, so by default others
  have no right to reuse the code. KataGo network licence text is already
  included for the model.
- **Options:** MIT or Apache-2.0 (permissive; Apache adds a patent grant);
  AGPL-3.0 (keeps hosted derivatives open); or no licence (all rights reserved).

### ADR-P10 One core crate plus two binding crates *(M0)*
- **Status:** Accepted 2026-11-03, as part of ADR-P01, which names exactly these
  three crates.
- **Decision:** `weiqi-core` contains `rules`, `sgf`, `zobrist`, `scoring` as
  modules; bindings are separate crates. Split modules into crates later only if
  build times or dependency isolation require it.

### ADR-P11 Arena-based SGF tree *(M1)*
- **Status:** Accepted 2026-11-07: built in M1 (`23ec86b`), which the owner
  approved and merged on 2026-11-06.
- **Decision:** Nodes in a `Vec` addressed by `NodeId(u32)`; no `Rc<RefCell<…>>`.
  Simpler ownership, iterative traversal, trivial serialisation.

### ADR-P12 Replay modes `Strict` and `Record` *(M1)*
- **Status:** Accepted 2026-11-07: built in M1 (`863ac83`), which the owner
  approved and merged on 2026-11-06.
- **Decision:** Manual entry rejects illegal moves; imported records are replayed
  as recorded with structured warnings, and the API decides whether flagged
  games may be analysed.

### ADR-P13 Japanese scoring takes explicit life-and-death input *(M1)*
- **Status:** Accepted 2026-11-07: built in M1 (`a62d6ad`), which the owner
  approved and merged on 2026-11-06.
- **Decision:** The scorer stays deterministic and takes dead stones and seki as
  input; the product proposes them from KataGo ownership and the user confirms.

### ADR-P14 Tag target and existing tag *(M0)*
- **Status:** Accepted by the owner, 2026-11-03.
- **Decision:** Tag `v0.1.0-prototype` on `eb089bc` (latest prototype work, the
  head of `codex/m5-deployment`); keep `archive/prototype-2026-08-27` (on
  `7447f54`, before the prototype's own v1 milestones) unchanged.

### ADR-P15 Python binding shape *(M2)*
- **Status:** Proposed 2026-11-07, built in M2 step 2; accepted when the owner
  approves M2.
- **Decision:** `weiqi-py` uses PyO3 0.30.1 with the `abi3-py314` stable ABI
  (one wheel per platform for Python 3.14 and later) and is packaged by maturin
  as the brand-free distribution `weiqi-core`. `python/` depends on it as a uv
  path source, so `uv sync` builds and installs the wheel. Values cross the
  boundary as owned copies in Python-native forms: colors `"B"`/`"W"`, points
  `(x, y)` tuples from the top left, moves a point or `"pass"`, hashes 128-bit
  ints, rule components as strings. Errors are `CoreError` subclasses with the
  core's `code`. The stub `weiqi_core.pyi` is written by hand and checked by
  `mypy.stubtest` in CI.
- **Context:** The conformance text forms (SGF letters, hex hashes) are for
  comparing transcripts; Python code is easier to type-check and index with
  tuples and ints. SGF ↔ point and GTP conversion stay in the core and will be
  exposed when the engine adapter needs them (M3).
