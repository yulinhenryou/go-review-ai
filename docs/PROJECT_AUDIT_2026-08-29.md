# Project Audit - 2026-08-29

Scope: real SGF workflow, report interaction, desktop/mobile UI, engine/release
logic, generated files, documentation, Git branches and GitHub Pages.

## High-impact Findings Resolved

| Finding | Risk | Resolution |
| --- | --- | --- |
| The last timeline move was treated as the post-game position | Users could not inspect the final move's evidence correctly | `null` now represents the terminal position; the last move remains navigable and has a tested transition to terminal state |
| Current-position and whole-game tabs rendered the same sections in a different order | Duplicate, long mobile reports and misleading navigation | Current view now contains active-position evidence/candidates; whole-game view contains overview, mistakes, markers and trend |
| SGF import required a native file field plus a second button | Redundant and cramped input flow | One `导入 SGF` command opens the chooser and parses immediately |
| Release checks required real KataGo but ignored the local app's engine discovery | A working local install could fail its release gate | `scripts/test_python.py` now reuses `engine_environment()` |
| KataGo created hundreds of ignored log files | Noisy workspace and unnecessary local game traces | Both engine configs set `logToFile = false`; generated logs/caches are cleaned and remain ignored |
| GitHub Pages served an obsolete monolithic prototype | Public repository presentation contradicted current code | Pages now builds a read-only current UI from sanitized real KataGo evidence |

## UI and Accessibility

- Increased base/report typography, control sizes and mobile targets; kept the
  operational two-column desktop layout and single-column mobile flow.
- Increased marker size and contrast while retaining shape plus color semantics:
  square for played/mistake, triangle for recommendation, numbered circle for candidates.
- Replaced CSS-drawn branding with the checked-in Lucide icon and removed the stale
  M4 label.
- Preserved keyboard focus, report tab state, text equivalents for board markers,
  and reduced-motion behavior. This is a focused implementation audit, not a full
  screen-reader or WCAG conformance certification.

## Repository and GitHub

- Runtime logs, caches, models, private uploads and build outputs remain excluded.
- `archive/` remains historical only and has no runtime imports.
- `main` should contain the tested local candidate; `gh-pages` contains only the
  generated static showcase. Milestone branches remain historical checkpoints.
- The public repository should use the Pages URL as its homepage and current
  Go/KataGo/SGF topics. No project license is added by this audit because choosing
  one changes redistribution rights and requires an owner decision.

## Remaining Boundaries

- Pages cannot upload/analyze new games because it has no Python/KataGo runtime.
- Public backend, Linux image acceptance and different-network review remain open M5 gates.
- Thresholds and low-visit estimates still require product calibration; the UI
  continues to expose coverage and quality warnings rather than hide uncertainty.
