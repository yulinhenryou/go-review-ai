# Roadmap

*Written 2026-11-03 and approved by the owner the same day. It replaces the
prototype's roadmap, now at `legacy/docs/ROADMAP.md`. Fupan is a provisional
name.*

| Milestone | State |
| --- | --- |
| M0 Archive, legacy move, skeleton, CI | Done — [acceptance](acceptance/M0.md) |
| M1 Rust rules engine and SGF parser | Done — [acceptance](acceptance/M1.md) |
| M2 Python bindings, WASM build and web shell | Done — [acceptance](acceptance/M2.md) |
| M3 KataGo adapter, cache and storage foundation | Acceptance recorded, in review — [acceptance](acceptance/M3.md) |
| M4–M8 | Not started |

## Rules for every milestone

- Starts only after the previous milestone's acceptance is recorded and the
  owner approves.
- Ends with the repository runnable, all CI jobs green (including `legacy`
  until it is deleted), and an acceptance record in `docs/acceptance/Mx.md`
  listing commands, inputs, versions, hardware and results.
- Any number in docs comes from that record. No performance targets are
  promised before they are measured.
- Changes of technical direction stop the work and go to the owner first.

## Adjustments to the suggested sequence

The owner's suggested order is kept, with three adjustments accepted by the
owner on 2026-11-03 (ADR-P04):

1. **Web work starts in M2, not M8.** WASM must be proven in a real browser when
   it is built, and deleting `legacy/` at the end of M4 would otherwise remove
   the only web interface. So M2 adds a minimal web shell (board with WASM
   rules), and M4 adds the new single-game review page needed for parity.
   M8 becomes design polish, deployment and the first public release.
2. **Storage starts in M3.** The analysis cache needs persistent storage, so the
   SQLite schema and migrations begin with the engine adapter rather than with
   the profile.
3. **Labelling sessions with the owner** are scheduled in M4 and M5: phase and
   situation classifiers need gold labels from a strong player before their
   statistics can be trusted.

## M0 — Archive, legacy move, monorepo skeleton and CI

**Goal:** a clean starting point where the prototype is preserved and still runs,
and an empty but fully wired monorepo passes CI.

Scope:

- Prerequisite (owner): accept the Xcode license.
- Tag `v0.1.0-prototype` (annotated) on `eb089bc` (ADR-P14); push it.
- `git mv` the prototype into `legacy/` (MIGRATION §3); legacy gets its own
  uv-managed environment.
- Install toolchains: rustup (stable + nightly for fuzzing), uv, maturin, wasm
  tooling; pin versions (`rust-toolchain.toml`, `.python-version`, Node version
  file).
- Skeleton: Cargo workspace with `weiqi-core` (one trivial function and test),
  `python/` uv project with package `weiqi` (one test), `web/` Vite + React + TS
  (one test), `config/project.json`.
- Lint and format configs: rustfmt, clippy, ruff, mypy strict, eslint, tsc.
- GitHub Actions: jobs `rust`, `python`, `web`, `legacy`; caching; required on PRs.
- Root `README.md` replaced by the approved draft; `AGENTS.md` becomes a
  pointer; `docs/ROADMAP.md` replaced by this file; Apache-2.0 `LICENSE` added
  (ADR-P09).

Acceptance:

1. `git show v0.1.0-prototype` shows the approved commit, and
   `git ls-remote --tags origin` lists the tag.
2. In `legacy/`: `pytest -q` passes with the same test count as before the move
   (302 passed, 7 skipped without live KataGo, as measured on 2026-11-03) and
   `node --test tests/frontend/*.test.mjs` passes 40 tests; the opt-in live suite
   also passes locally; the legacy local web workspace starts and completes a
   review of `samples/sample_game.sgf`.
3. A fresh clone runs `cargo test`, `uv run pytest`, `npm test` and all
   linters successfully with the documented commands.
4. All four CI jobs are green on the M0 PR.
5. `git log --follow legacy/src/game.py` shows the file's prototype history.

## M1 — Rust rules engine and SGF parser

**Goal:** the single authoritative implementation of board rules, scoring,
hashing and SGF.

Scope: ARCHITECTURE §3 — board, captures, suicide policy, simple ko,
positional and situational superko, rule-set presets, setup stones and
handicap, `Strict` and `Record` replay modes, Zobrist (128-bit, deterministic
keys), area and territory scoring with explicit life-and-death input, SGF
decode/lex/parse/arena tree/extract/write, encodings, leniency warnings,
limits. Each Rust concept used is explained to the owner before the code.

Acceptance:

1. All ported prototype rule and SGF cases (MIGRATION G02, G08, G10) pass, with
   every intentionally changed expectation listed in the PR.
2. Proptest properties pass: incremental hash = recomputed hash; undo restores
   state; stone conservation (stones placed − captured = stones on board);
   SGF `parse(write(tree)) == tree`.
3. Fuzz targets for decode, parse and round-trip run for a recorded duration
   locally without crashes or panics; CI runs a short time-boxed fuzz job.
4. Scoring tests cover Chinese and Japanese results on hand-checked final
   positions, including captures, dead stones and a seki case.
5. Real-world SGF corpus (public files with provenance, including a GBK file
   and a multi-variation file) parses with expected warnings.
6. `cargo clippy -D warnings`, `cargo fmt --check`, `#![forbid(unsafe_code)]`.
7. Benchmarks (criterion) for replaying a 300-move game and parsing a large SGF
   are recorded as a baseline, without targets.

## M2 — Python bindings, WASM build and web shell

**Goal:** the same Rust core is usable from Python and the browser, and the
three agree.

Scope: `weiqi-py` (PyO3 + maturin, `.pyi` stubs), `weiqi-wasm`
(wasm-bindgen, TS types), shared golden conformance cases, a minimal web page:
SVG board, manual entry with WASM legality (captures, ko, pass, undo), SGF file
open and move navigation. No analysis yet.

Acceptance:

1. The golden conformance suite produces identical positions, hashes and
   warnings in Rust, Python and WASM (CI).
2. `mypy --strict` passes against the stubs; Python tests import `weiqi_core`
   from a wheel built in CI.
3. Browser end-to-end test (Playwright) places stones, captures, rejects an
   immediate ko recapture and suicide, passes and undoes, without a server call.
4. WASM bundle size and Python wheel build time are measured and recorded.
5. Each binding's ownership/borrowing boundary (what is copied, what is
   borrowed) is documented and explained.

## M3 — KataGo adapter, cache and storage foundation

**Goal:** reliable, reproducible, cancellable real-engine analysis.

Scope: ARCHITECTURE §5 — asyncio process supervisor, JSON query model,
`analyzeTurns` whole-game queries, strict response parsing (ported), BLACK-
perspective normalisation, ownership, `terminate`-based cancellation, timeouts,
restart, readiness and provenance, `query_key` cache with `stones_hash` index,
SQLite schema and Alembic migrations (also tested on PostgreSQL in CI), recorded
fixtures, benchmark tool.

Acceptance:

1. Ported engine tests (MIGRATION E08) pass against the async adapter.
2. Recorded-response replay reproduces every normalised field except timing and
   ids.
3. Opt-in live tests: a short game and the 235-move benchmark complete with full
   provenance; cancel mid-game terminates queries and the process stays usable;
   killing the engine process fails pending queries cleanly and the supervisor
   restarts it.
4. Re-analysing the same game hits the cache for every position (0 engine
   queries), verified by counters.
5. Benchmarks recorded on named hardware/model/visits: wall time and peak RSS for
   the 235-move game, cold and warm process.
6. Migrations apply on SQLite and PostgreSQL in CI.

## M4 — Single-game metrics, review page, comparison and legacy removal

**Goal:** the new pipeline matches and exceeds the prototype on single-game
review; then `legacy/` is deleted.

Scope: ARCHITECTURE §6 — score loss (definitions per ADR-P02), winrate delta,
ownership delta, group status changes, turning points, severity with the
default calibration band, coverage and partial results, result schema, CLI,
API (games, analyses, jobs with SSE progress and cancel), and a web review page
(upload, metadata confirmation, progress, cancel, loss timeline that jumps to
positions, mistake list, markers). First labelling session: the owner labels
phase boundaries on a sample of their games.

Comparison suite (legacy vs new, same model, config and visits):

- **Noise envelope first:** run legacy twice on each corpus game and record the
  run-to-run spread of its per-move loss and its top-mistake set. Tolerances for
  the comparison are set from this measured spread, before seeing new results.
- Corpus: `sample_game`, `m3_mistake`, `benchmark_pro_game` (235 moves), the
  111-move game (`test_game_kejie`), and malformed/unsupported inputs.
- Checks: identical accept/reject decisions for inputs legacy supports; the new
  same-root diagnostic agrees with legacy loss within the envelope; top-mistake
  sets overlap within the envelope; every legacy warning type has an equivalent.

Acceptance:

1. Ported metric and report tests (MIGRATION R01–R07) pass.
2. The comparison suite passes.
3. "Exceeds" is demonstrated with tests: handicap/setup-stone games, a non-UTF-8
   SGF, a multi-variation SGF, cached re-analysis, persisted results, ownership-
   based group status facts, all of which legacy cannot do.
4. Browser end-to-end tests cover upload, manual entry, confirmation, progress,
   cancel, timeline jump and mistake selection on desktop and mobile widths,
   including one run against real KataGo.
5. Every MIGRATION item is Done or Dropped; the owner approves; `legacy/` is
   removed in one commit; CI stays green.

## M5 — Multi-game import and player profile

**Goal:** answer "where am I weak?" across many games.

Scope: bulk SGF import (folders/archives, duplicate detection by content and
moves), player identity across names, batch analysis with priorities, phase
and situation classifiers v1, game-level aggregation, cluster-bootstrap
intervals, trends, comparability strata, profile API and interactive profile
view. Second labelling session: the owner labels situation types on sampled
positions.

Acceptance:

1. Importing the owner's corpus (private, never committed) completes; duplicates
   are reported.
2. Each classifier's precision and recall against the owner's labels are
   measured and recorded; a classifier below the owner-approved bar is shown
   as experimental or hidden.
3. Statistical code is tested on synthetic data with known answers (interval
   coverage close to nominal in simulation).
4. Profile cells below the minimum sample size show "insufficient data".
5. The owner reviews their profile and records whether it matches their own
   assessment (qualitative acceptance, written down).

## M6 — Explanation layer

**Goal:** bilingual explanations built only from facts.

Scope: fact extraction, template catalog keyed by facts and strength band,
`zh-CN` and `en` locales, glossary of Go terms, explanation views. No LLM in
this milestone.

Acceptance:

1. Every template has tests with fixed fact inputs, in both languages.
2. A checker verifies that every coordinate, number and move in rendered text
   exists in the input facts; it runs on all fixtures in CI.
3. The owner reviews a sample of explanations for correctness and terminology,
   and the review is recorded; corrections become test cases.

## M7 — Training loop

**Goal:** review → diagnose → practise → measure again.

Scope: exercise generation with deep re-analysis, acceptable-answer sets by
strength band, deduplication by `stones_hash`, answer checking with on-demand
engine evaluation, spaced-repetition scheduler (ADR-P05), review log, practice
UI, re-measurement of linked weaknesses in later games.

Acceptance:

1. Exercises are generated from the owner's games, and every acceptable answer
   is traceable to stored engine evidence.
2. A non-precomputed answer is never graded without an engine evaluation.
3. Scheduler tests reproduce the chosen algorithm's reference examples.
4. The owner uses the loop for an agreed period; the re-measurement report shows
   before/after values with intervals and states the limits of the inference.

## M8 — Design polish, deployment and first public release

**Goal:** a refined, deployable product.

Scope: full visual design pass (typography, spacing, palette, motion), strength
calibration settings UI, accessibility, privacy and retention policy, public
deployment (container, hosting chosen with a spending limit approved by the
owner), security controls from the prototype's public mode, release process,
README with verified facts only.

Acceptance:

1. A fresh checkout builds and deploys with the documented process.
2. A user on another device and network completes import → profile → practice.
3. Security checks (upload limits, rate limits, safe rendering, no private data
   in logs) pass.
4. Release notes list measured performance, known limitations and the exact
   engine/model used.
