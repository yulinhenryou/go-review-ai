# AGENTS.md

## Project Goal

Deliver a first web release that:

1. accepts one uploaded SGF or a game manually entered on a board
2. parses and validates the game
3. analyzes it with real KataGo
4. highlights obvious mistakes with engine-backed evidence
5. displays a concise review report in the browser

The original CLI-only phase is the prototype baseline. Keep the CLI as a useful
development entry point, but the next release includes the web workflow.
The user approved `docs/ROADMAP.md` on 2026-08-27. M1 implements the shared input
contract; continue milestone by milestone with acceptance evidence.
See `docs/INPUT_CONTRACT.md` before changing parser, API or engine input semantics.

## Rules

- Keep modules small and testable.
- Separate parsing, engine integration, analysis, classification, and report generation.
- Prefer deterministic templates over free-form explanation.
- Do not invent Go explanations, scores, or variations unsupported by engine output.
- Treat current mock fallback and heuristic teaching as prototype debt, not v1 behavior.
- Keep mock data out of the future production path; retain explicit test/demo use.
- Add tests for important changes; mock-only tests do not validate real KataGo.
- Keep `archive/` out of runtime imports, default inputs, and published assets.
- Preserve existing behavior during housekeeping; replace coupled prototype modules with tests in the planned milestones.
- Keep logs, private SGFs, secrets and model weights out of Git.
