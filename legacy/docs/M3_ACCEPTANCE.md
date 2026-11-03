# M3 Acceptance Record

Date: 2026-08-28. Branch: `codex/m3-factual-report`, based on M2 `aba1ee0`.
Status: **M3 gate satisfied on the tested local environment; not a public web release**.
The preceding rule/komi-control fix is included in this source update.
The final combined verification is in [M1-M3 regression](M1_M3_REGRESSION.md).

## Delivered

- Default obvious/severe point-loss thresholds 3.0/5.0; configurable with shared
  validation, with summary limit 1-5 and default 5.
- Ranking by unrounded loss then move number, no padding; all chronological
  mistake markers remain separate from the ranked summary.
- Factual Chinese move summaries, actual/recommended moves, optional moving-player
  winrate change in percentage points, genuine candidate-owned PVs and provenance.
- Coverage-aware complete/partial/no-qualifying-mistake states. Missing values
  stay null; unavailable moves are not classified as clean. A fully evaluated
  partial record is still labeled unfinished/unknown, not a completed game.
- Search noise, separate searches, missing values/PVs and low visits stay visible.
- Retired classifier, key-point and teaching modules and their obsolete tests;
  historical source remains in Git, not runtime imports or the wheel.
- Review schema 3.0 with API, CLI templates and browser consumers migrated
  together. Breaking fields and compatibility rules are in [report contract](REPORT_CONTRACT.md).
- Browser summary, quality notes, provenance, all markers, pre-move navigation,
  actual/recommended markers and charts that break across unavailable evaluations.
- README, input/engine/report contracts, roadmap, status and archive index updated.

## Verification

- Final Python run with live KataGo enabled: **253 passed, no skips**, 34.47 s
  on this local run. This includes 248 regular/recorded tests and 5 live cases.
- Frontend Node tests: **14 passed**, including the prior 8 rule/komi tests and
  6 report tests for coverage, all markers, escaping, provenance and chart gaps.
- Fixed-evidence tests cover exact 3/5 boundaries, unrounded ranking/ties,
  fewer-than-five/zero mistakes, missing scores/winrates/current values, pass,
  negative differences, both player perspectives, input validation, mismatched
  context, finite-value overflow, source notices and retired imports.
- The saved M2 real JSONL response fixture still reproduces normalized evidence
  exactly. Its report transformation now verifies white-player loss and the
  matching candidate PV. Exact fixtures are not treated as live strength evidence.
- Real M3 six-move input was rerun twice in each final integration run at
  maxVisits 200. All runs identified moves 1, 3 and 5; losses were within the
  documented 4-point tolerance of the saved observation. Ranking and recommended
  coordinates are not required to be bit-for-bit identical across searches.
- Existing real-engine tests still cover traceable analysis and Japanese/Chinese
  two-pass endings. Engine failures still have no simulated fallback.
- `git diff --check` passed. All 19 production Python modules parse.

Commands (set engine paths as in README):

```bash
python -m pytest -q -ra
RUN_KATAGO_INTEGRATION=1 python -m pytest -q -ra
node --test tests/frontend/*.test.mjs
python -m pip wheel --no-deps --wheel-dir /tmp/go-review-m3-wheel .
```

### Browser Smoke

The following is the initial M3 smoke, before the follow-up UI/local-service fix.
The current unified local entry point and marker design are covered in
[local workspace acceptance](LOCAL_WORKSPACE_ACCEPTANCE.md).

Initial frontend `http://localhost:3000`, API `http://127.0.0.1:8000`:

- Uploaded `samples/m3_mistake.sgf` through the actual file chooser and upload
  button. Real KataGo returned schema 3.0, 6/6 point-loss and winrate coverage,
  three severe mistakes and a separate-search caveat.
- Clicking the first mistake showed the empty pre-move board, red actual marker
  at A19 and the recommended-point cross. Clicking move 6 showed the five-stone
  pre-move board, not the final-position recommendation. Navigation controls and
  chronological markers remained usable.
- Manually entered Black A1 and White Q4 on the board, then analyzed with Chinese
  rules/7.5 komi. Real engine result: 2/2 coverage, one severe mistake, visible
  low-visit/separate-search warnings. The final browser version was reloaded
  before this test; no console errors were reported.
- Desktop screenshot inspection and 390x844 mobile screenshot inspection covered
  board, controls, report and wrapped engine provenance. Mobile document width
  and scroll width were both 390; no horizontal overflow was observed. Temporary
  viewport overrides were reset afterwards.
- Partial/error rendering is covered by API and Node fixtures, not a claim that
  every failure state was induced in this browser smoke. Full browser automation,
  stale-response handling, queueing and cancellation remain M4 acceptance work.

### Real Observation

Source: [sanitized observation](evidence/m3-report.json), from a public synthetic
six-move sample created for M3. No private game, model weights, local paths or
raw server logs are included.

| Move | Actual | Recommendation in this run | Estimated loss | Moving-player winrate change |
| --- | --- | --- | --- | --- |
| 1 Black | A19 | R16 | 12.60 points | -35.98 percentage points |
| 3 Black | B19 | D16 | 12.01 points | -0.82 percentage points |
| 5 Black | C19 | F17 | 9.58 points | -0.08 percentage points |

Hardware/model: Apple M4 / 16 GiB; KataGo 1.16.4 Metal;
`kata1-b18c384nbt-s9996604416-d4316597426`, hashes in the observation. This is
acceptance evidence for the pipeline, **not a calibrated teaching/strength test**.
No tactical cause is inferred from these values.

### Packaging

The old ignored `build/` cache contained retired modules. It was moved to
`/tmp/go-review-m3-build-before-20260828` before a fresh isolated wheel build.
The new wheel has 23 entries and contains no retired modules, mocks/tests,
archive, samples or frontend assets. It was loaded directly from the wheel
outside the checkout using the existing environment's dependencies; service/API
imports and input validation passed. This is not a new full platform/install matrix.

## Remaining Boundaries

M3 completes factual selection/reporting on the local environment. It does not
complete web v1. M4 still owns bounded jobs, cancellation, stable input snapshots,
full pass/metadata-confirmation UX, shared board-state refactoring and comprehensive
browser acceptance. M5 owns backend hosting, HTTPS, resource/abuse limits and
second-device verification. The Pages site remains the older static prototype.
Source synchronization to GitHub does not deploy the API or update the Pages branch.
