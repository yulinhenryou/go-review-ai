# Local Workspace Acceptance

Date: 2026-08-28. Branch: `codex/m3-factual-report`.
Scope: localhost availability and board/report usability after M3.
This workspace improvement is included in the M3 source update.
See [M1-M3 regression](M1_M3_REGRESSION.md); Pages publication remains separate.

## Cause and Fix

The reported `ERR_CONNECTION_REFUSED` was reproduced with no listeners on
ports 3000 or 8000. The former terminal-owned servers were no longer running.

- `app.local:app` serves only `frontend/` plus the API on one loopback origin.
- The frontend uses relative API URLs; it no longer needs a second server.
- The macOS launcher bootstraps an on-demand launchd user job, independent of
  the conversation/terminal. No login startup is installed. Stop/restart target
  only the job identified by this checkout's path hash.
- State and logs live in ignored `.local/`. Models and private SGFs are not added.
- Port selection avoids another listener. `SO_REUSEADDR` avoids mistaking the
  previous service's TIME_WAIT sockets for an occupied port.
- Restart waits for launchd to finish removing the previous job.
- Local responses use `Cache-Control: no-store` to avoid stale frontend modules.
- SGF analysis is offloaded from the async route to the thread pool. A regression
  test checks that health requests finish while analysis is blocked.

Live start, stop/restart and repeated start were checked. The final service URL
is `http://localhost:3000/`. Repeated start during a real SGF analysis returned
the same URL, rather than a second service or an unavailable error.

## UI Behavior

- Neutral workspace layout, local Lucide toolbar icons and a responsive board.
- Red square **!**: an engine-evaluated mistake. Gray square: another actual
  move. Green triangle: recommendation. Blue numbered circle: other candidate.
- Actual/recommendation collisions become one green **=** marker. Actual/other
  candidate collisions retain the actual marker and the candidate's selection
  rank. These combinations are covered by deterministic unit tests.
- Candidate numbers and recommendations use the active move's evidence,
  including immediately after automatic top-mistake selection.
- Coordinates, text equivalents and optional move numbers improve readability.
  Candidate visibility can be toggled without hiding the actual/recommended
  evidence. Selecting another candidate from the report makes it visible again.
- Unknown/under-threshold moves are not assigned the red mistake symbol.
  Passing/unavailable coordinates do not produce an invented board point.
- Review mode rejects accidental board edits, even at the final position.
  Explicit continue-entry, placement and undo were checked.
- Input mutation and duplicate submissions are disabled during a request.
  This is not a persistent job queue or cancellation implementation.
- On mobile, selecting a mistake from the report brings its board into view.

## Verification

- Python: **276 passed**, including **5 live KataGo tests**, no skips; 40.93 s.
- JavaScript: **23 passed**: 9 board-marker, 8 rule/komi and 6 report tests.
- New local tests cover same-origin API/static serving, private-path exclusion,
  no-store headers, port collisions, idempotence, scoped stop and health identity.
- Browser upload through the real file chooser: `samples/m3_mistake.sgf`,
  KataGo provenance, 6/6 coverage and mistakes at moves 1, 3 and 5. Repeated
  searches produced slightly different estimates, as expected.
- Manual browser entry: Black K10 (`jj`), White L10 (`kj`), Chinese rules,
  komi 7.5. Real KataGo returned 2/2 coverage and the same played coordinates.
- Candidate selection, hide/reveal, move navigation and final-position
  read-only behavior were checked with browser interactions.
- Chinese 7.5 / Japanese-Korean 6.5 presets and editable custom 5.5 were
  checked without changing recorded SGF metadata.
- Desktop 1360x1000 and mobile 390x844 / 320x740 layouts were inspected.
  Both mobile document widths matched their viewport widths, without horizontal
  overflow. Board labels, markers, settings and wrapping controls were checked.
- Browser console checks reported no errors or warnings in the tested flows.

Commands:

```bash
RUN_KATAGO_INTEGRATION=1 python -m pytest -q -ra
node --test tests/frontend/*.test.mjs
python scripts/local_server.py start
python scripts/local_server.py restart
python scripts/local_server.py status
git diff --check
```

## Boundaries

The background launcher is macOS-only; foreground Uvicorn remains the POSIX
alternative. The checkout and existing virtual environment are required.
Log out/reboot ends this on-demand service; start it again afterwards.
Closing a browser tab does not stop it.

M4 still owns bounded analysis jobs, progress/cancellation, full pass/input UX
and comprehensive automated browser acceptance. M5 still owns public backend
hosting and resource/abuse controls. GitHub Pages remains the older prototype;
this local server is not a public deployment.
