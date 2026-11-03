<!--
Draft README, written 2026-11-03. Replace the root README.md only after the
owner approves and M0 has created the tag and the legacy/ directory; check every
statement marked "verify after M0" before publishing. Relative links are written
for the root location, so they resolve only after the file moves to README.md.
-->

# Fupan

Fupan is a Go (Weiqi / Baduk) game-review project: it turns a player's own games
into a diagnosis and a training plan.

> **Status: early development, under active rebuild.** There is no usable
> release of the new design yet. Nothing below the "Vision" heading describes
> shipped features.

*Fupan is a provisional name.* It comes from 复盘 (fùpán), the Go tradition of
replaying a finished game to find where it was won and lost.

## Where this project comes from

This repository started as **Go Review AI**, an early experiment that reviewed a
single game with KataGo: SGF parsing and validation, real KataGo analysis with
recorded provenance, mistake selection by estimated point loss, short factual
Chinese summaries, a FastAPI service and a browser board with progress and
cancellation.

That prototype is preserved under the Git tag `v0.1.0-prototype` and, during the
rebuild, runs unchanged from the `legacy/` directory (verify after M0). It will
be removed from the main tree only after the new implementation matches it in
comparison tests; it always remains available in Git history.

## Vision

Single-game "which move lost the most points" is already well served by tools
such as KaTrain. Fupan aims at the questions that come after:

1. **Player profile** — across many games, where are the points lost: by phase
   (opening, middle game, endgame) and by situation (life and death, invasion,
   ko, endgame), with trends and confidence intervals.
2. **Explanations with reasons** — built only from engine evidence (variations,
   score and ownership change, which group's status changed), in Chinese and
   English with standard Go terminology. No invented reasoning.
3. **Closed-loop training** — mistakes from your own games become exercises,
   scheduled with spaced repetition, and progress is measured again in later games.
4. **Calibrated to your level** — what counts as a mistake, and what an
   explanation emphasises, depends on the player's strength.

Fupan is not a playing engine, does not train neural networks, and does not try
to compete with Sabaki or KaTrain as a board editor.

More: [Vision](docs/VISION.md) · [Architecture](docs/ARCHITECTURE.md) ·
[Roadmap](docs/ROADMAP.md) · [Decisions](docs/DECISIONS.md) ·
[Migration](docs/MIGRATION.md)

## Planned architecture

| Part | Technology |
| --- | --- |
| Rules core (rules, scoring, SGF, Zobrist hashing) | Rust, shared with Python via PyO3 and with the browser via WebAssembly |
| Analysis and service layer | Python (asyncio, FastAPI), using the [KataGo](https://github.com/lightvector/KataGo) analysis engine |
| Web app | TypeScript, React, Vite |
| Storage | SQLite, designed to move to PostgreSQL |

## Current status

| Area | State |
| --- | --- |
| Planning documents | Written; under review |
| Prototype (`legacy/`) | Runs locally with its own environment (verify after M0) |
| Rust core, Python layer, web app | Not started |

Progress is tracked milestone by milestone in the [roadmap](docs/ROADMAP.md).
Each milestone records its acceptance evidence; this README only states facts
that have been tested.

## Requirements and setup

Setup instructions will be added when the first milestone that produces runnable
code is complete. KataGo binaries and network weights are not part of this
repository; see the [KataGo network licence](licenses/KATAGO_NETWORK_LICENSE.txt)
for the model used by the prototype.

## Licence

Apache License 2.0; see [LICENSE](LICENSE) (verify after M0). KataGo and its
networks are separate projects under their own licences.
