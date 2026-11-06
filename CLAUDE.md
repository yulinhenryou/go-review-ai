# CLAUDE.md

Project guide for every working session. Read this first, then the documents it
links. Keep it short and current; move history into `docs/DECISIONS.md`.

## 1. What this project is

**Fupan** (provisional name, see §6) is a Go (Weiqi / Baduk) game-review project
being rebuilt from the early prototype *Go Review AI*.

> Fupan turns your games into a diagnosis and a training plan.

Single-game "find the biggest point loss" is already well served by open-source
tools such as KaTrain. Fupan instead aims at four pillars (details in
[docs/VISION.md](docs/VISION.md)):

1. **Player profile** across tens to hundreds of games: loss distribution by game
   phase and situation type, trends over time, with confidence intervals.
2. **Reasoned explanations** built only from deterministic, engine-backed facts
   (variations, score change, ownership change, which group's status changed),
   in Chinese and English with standard Go terminology.
3. **Closed-loop training**: the player's own mistakes become exercises scheduled
   by spaced repetition, and learning is re-measured.
4. **Strength calibration**: thresholds and explanation focus depend on the
   player's level.

Non-goals: no playing engine, no neural-network training, no competition with
Sabaki or KaTrain on board editing.

**Current phase (2026-11-06): M0 and M1 merged to `main`; M2 (Python
bindings, WASM build and web shell) not started.**
The plan is in [docs/ROADMAP.md](docs/ROADMAP.md),
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md), [docs/MIGRATION.md](docs/MIGRATION.md)
and [docs/DECISIONS.md](docs/DECISIONS.md); acceptance records live in
`docs/acceptance/`. The prototype's own docs and agent guide are historical
material under `legacy/`; root `AGENTS.md` only points here.

## 2. Working agreement with the owner

The owner is Henry, an amateur 4-dan who has studied AlphaGo and KataGo and is the
first real user. Fluent in Python, Java and JavaScript; new to Rust.

- **Reply in Chinese** for all conversation, explanations, plans and summaries.
- **Write English** in public repository text: README, `docs/`, code comments,
  commit messages.
- **Explain before coding.** State the principle or algorithm first, then write
  the code; explain key code line by line when asked or when it is non-obvious.
- **Rust teaching:** whenever Rust code is written, explain the ownership,
  borrowing, lifetime and trait mechanics that the code actually relies on.
  Prefer designs that keep these mechanics simple (owned data, indices into
  arenas, no public lifetimes) unless there is a measured reason not to.
- **Stable direction.** Once a technical route is decided (see DECISIONS), do not
  switch it. If a change of direction seems necessary, stop and ask first.
- **Never fabricate** analysis results, Go explanations, variations or
  performance numbers. README and docs state only facts that were tested or
  measured, with the command, input, engine/model and hardware where relevant.
- **No unrequested git operations.** Commit, tag, branch, push, move or delete
  only after the owner approves the specific step. Planning sessions add
  documents only.
- **Milestone discipline.** Work milestone by milestone; each closes with
  acceptance evidence and leaves the repository runnable with tests passing.

## 3. Core principles

- **Evidence first.** Every number, recommendation and explanation in a report
  must trace to recorded engine output plus deterministic code. Missing evidence
  stays missing; never substitute defaults (no 50% winrate, no utility-as-points,
  no stitched or padded variations).
- **Deterministic before generative.** Classification and explanation use
  versioned, deterministic rules and templates. An LLM may later rephrase text,
  but only from structured facts, with every coordinate and number validated
  against those facts.
- **One rules authority.** Board rules, SGF parsing and position hashing live in
  the Rust core only. Python and the browser call it; they never re-implement it.
- **Reproducibility.** Every analysis records engine version, model hash, config
  hash, visits, rules, komi, overrides and the metric definition version.
- **Honest uncertainty.** Thresholds are product settings to calibrate, not Go
  truths. Aggregates show sample size and confidence intervals. Search noise
  (e.g. negative differences) is flagged, never turned into praise.
- **Layered and testable.** Rules core → engine adapter → metrics → diagnosis &
  profile → explanation → training → API → frontend. Each layer depends only on
  layers to its left and is testable on its own.
- **Mocks are test doubles only.** No mock or demo data on the production path.
  Mock-only tests do not validate real KataGo behavior.
- **Privacy.** Private SGFs, logs, secrets, databases and model weights never
  enter Git or published assets.

## 4. Relationship to the prototype

The prototype (Python + sgfmill + KataGo + FastAPI + vanilla JS) is the
behavioral baseline, not a design constraint. Validated ideas, metric
definitions, tests and some logic are kept, referenced or ported per
[docs/MIGRATION.md](docs/MIGRATION.md); when they conflict with the rebuild goals,
the rebuild goals win.

Decisions carried over (see DECISIONS ADR-001 to ADR-011): `score_loss` in points
is the primary mistake metric; `winrate_delta` (percentage points) is kept as a
secondary signal; meaningful turning points are identified; no artificial
"top 3" cap; JSON output stays available for debugging; Chinese explanations for
East Asian users (now bilingual).

## 5. Migration strategy (summary)

Full plan: [docs/MIGRATION.md](docs/MIGRATION.md) and ROADMAP M0.

1. Tag the final prototype commit `v0.1.0-prototype` (the earlier tag
   `archive/prototype-2026-08-27` stays as is).
2. Move the prototype wholesale into `legacy/` with `git mv`; it keeps its own
   environment and must stay runnable and tested in CI during the transition.
3. Build the new monorepo at the root. New code never imports from `legacy/`.
4. Replace capabilities layer by layer. Delete `legacy/` only after the new
   single-game pipeline matches or exceeds it and passes the comparison tests
   (ROADMAP M4).
5. Keep full history; every milestone ends runnable and green; Conventional
   Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `build:`, `ci:`,
   `chore:`), with scopes such as `feat(rules): ...`.

## 6. Naming

"Fupan" (复盘, the traditional post-game replay to find gains and losses) is a
**provisional** name. "GoMind" was rejected: it collides with an existing Go-language
neural-network library and suggests a Golang project. The README's first
sentence must say this is a Go (Weiqi / Baduk) project.

Rules:

- The brand appears only in a few central places (list below). Code never
  hard-codes it; runtime code reads `config/project.json` (planned in M0).
- Internal crates, packages, modules, types, functions and environment variables
  are named by function (`rules`, `sgf`, `engine`, `metrics`, `profile`, ...),
  never with a brand prefix. The stable internal namespace is `weiqi`
  (DECISIONS ADR-P01, accepted 2026-11-03), which never changes on a rename.
- The owner renames the GitHub repository on the web; update the git remote after.

**Rename checklist** (keep this list exact when files are added or moved):

| Location | What to change | Exists now? |
| --- | --- | --- |
| `CLAUDE.md` | Title line and §1, §6 prose | yes |
| `docs/VISION.md`, `docs/ARCHITECTURE.md`, `docs/MIGRATION.md`, `docs/ROADMAP.md`, `docs/DECISIONS.md`, `docs/acceptance/*.md` | Prose mentions | yes |
| `README.md` | Title, first sentence | yes |
| `config/project.json` | `name`, `slug`, `tagline` (single runtime source) | yes |
| `python/pyproject.toml` | `[project].name` = slug (checked by `python/tests/test_project.py`) | yes |
| `web/package.json` | `name` = `<slug>-web` (checked by `web/src/App.test.tsx`) | yes |
| `web/index.html` | `<title>` fallback (runtime title from config) | yes |
| `python/uv.lock`, `web/package-lock.json` | Regenerated by `uv lock` / `npm install` after the two edits above | yes |
| Deployment config (container image / app name) | Image and service names | planned M8 |
| GitHub repository and `git remote` URL | Repository name | owner action |

Rust crates carry no brand (`weiqi-core`, `weiqi-py`, `weiqi-wasm`), so
`Cargo.toml` files need no change on rename.

## 7. Technology stack (target)

| Area | Choice |
| --- | --- |
| Core library | Rust: rules (moves, captures, ko, superko, Chinese area / Japanese territory scoring), SGF parser (variations, comments, malformed files, legacy encodings), Zobrist hashing |
| Bindings | PyO3 + maturin for Python; wasm-bindgen for WebAssembly |
| Analysis & service | Python, asyncio KataGo analysis-engine adapter (JSON protocol), batching, cache, timeouts, cancellation; FastAPI |
| Frontend | TypeScript + React + Vite; board legality via the WASM core |
| Storage | SQLite first, schema portable to PostgreSQL |
| Tooling | uv (Python), cargo (Rust), npm (web), GitHub Actions (`.github/workflows/ci.yml`: jobs rust, python, web, legacy) |
| Versions (ADR-023) | Rust 1.99.1, edition 2024; Python 3.14; Node ≥ 22.12 (CI: 24); TypeScript 6.0.3 until typescript-eslint supports 7 |
| Lint / format / types | `cargo fmt`, `cargo clippy -D warnings`, `ruff check`, `ruff format`, `mypy --strict`, `eslint`, `tsc -b` |

Layout (M0 created `crates/weiqi-core`, `python/`, `web/`, `config/`, `legacy/`;
the rest arrives in M1–M3):

```text
crates/weiqi-core/   rules, sgf, zobrist, scoring (pure Rust, no I/O)
crates/weiqi-py/     PyO3 bindings -> Python module `weiqi_core`
crates/weiqi-wasm/   wasm-bindgen bindings -> web package
python/              uv project; package `weiqi` (engine, metrics, profile, explain, training, storage, api)
web/                 Vite + React + TypeScript app
config/              project.json, KataGo configs (no weights)
testdata/            public SGF corpus with provenance, recorded engine responses
legacy/              prototype during transition (deleted after M4)
docs/                English public documentation
```

## 8. Code conventions

- **General:** small modules with one responsibility; pure functions where
  possible; explicit types at boundaries; no global mutable state; errors carry
  stable machine-readable codes plus messages; no brand names in identifiers.
- **Rust:** edition 2021 or later (pin in M0); `#![forbid(unsafe_code)]` in
  `weiqi-core`; no panics on untrusted input (SGF parsing returns `Result`);
  `thiserror` for error types; public API uses owned types and indices, not
  borrowed lifetimes; doc comments on every public item.
- **Python:** `mypy --strict` clean; frozen dataclasses or Pydantic models at
  boundaries; asyncio for engine I/O; no blocking calls in the event loop;
  layer imports enforced (import-linter or equivalent, decide in M0).
- **TypeScript:** `strict: true`; no `any` in committed code; UI never computes
  Go rules itself — it calls the WASM core; analysis values come only from the API.
- **Text:** user-facing strings live in locale catalogs (`zh-CN`, `en`), not in
  result builders. Results carry codes and numbers; rendering chooses language.
- **Comments:** English, explain *why*; match surrounding density.

## 9. Testing requirements

- Every important change ships with tests. A green suite of mocks is not proof of
  real-engine behavior.
- **Rust core:** unit tests per rule; `proptest` properties (e.g. incremental
  Zobrist equals recomputed hash; stone conservation; SGF write→parse round-trip);
  `cargo-fuzz` targets for the SGF parser (short runs in CI, longer runs on demand).
- **Bindings:** the same golden cases run through Rust, Python and WASM and must agree.
- **Engine adapter:** recorded real KataGo responses (sanitized, with provenance)
  for deterministic tests; opt-in live tests (`RUN_KATAGO_INTEGRATION=1`) for
  each milestone that touches engine behavior; live results use tolerances.
- **Metrics / profile:** fixed evidence fixtures cover thresholds, ties,
  missing data, both colors and pass; statistical code tested against known
  distributions.
- **Frontend:** unit tests (Vitest) for state and rendering logic; browser
  end-to-end tests (Playwright, decide in M2) for the main flows on desktop and
  mobile widths.
- **Legacy:** `legacy/` tests keep passing in CI until `legacy/` is deleted.
- Record acceptance evidence per milestone (commands, inputs, versions, results).

## 10. Environment notes

- Owner's Mac (2026-11-03): Xcode license accepted, so git and the Rust linker
  work. uv and rustup are installed via Homebrew; rustup is keg-only, so shells
  need `export PATH=/opt/homebrew/opt/rustup/bin:$PATH` (in the owner's
  `~/.zshrc`; non-interactive agent shells prefix commands with it). The
  nightly toolchain (minimal profile) and `cargo-fuzz` 0.13.2 were installed in
  M1 (2026-11-04); fuzzing runs from `crates/weiqi-core/fuzz/`, whose own
  `rust-toolchain.toml` selects nightly. maturin, wasm-bindgen tooling and
  Playwright are installed in the milestone that first needs them.
- `legacy/` uses its own `legacy/.venv` (Python 3.14, created with uv from
  `legacy/constraints.txt`); run its commands from inside `legacy/`.
- Real KataGo 1.16.4 and three models are installed under `/opt/homebrew`
  locally; weights are never committed.
