# M1 Acceptance Record

Date: 2026-08-27. Branch: `codex/m1-input-contract`.
Scope approved by the user before implementation.

## Delivered

- Immutable shared game/move records and all-position replay snapshots.
- sgfmill parsing and captures with strict input boundaries and legality checks.
- Rules/komi confirmation, root-node moves, pass handling and variation warnings.
- Engine-free preview endpoints and validation before engine creation.
- Explicit pass versus current-position requests; rules forwarded to KataGo.
- Review schema 2.1 adds rules, record status and input warnings.
- Minimal frontend metadata/error integration, without a framework rewrite.
- Pinned dependencies, explicit package discovery and installable Python wheel.

## Automated Evidence

Commands run in the project environment and an independent fresh virtualenv:

```bash
python -m pip install -c constraints.txt '.[api,dev]'
python -m pytest -q -ra
python -m pip check
```

Result: **173 passed**, no skipped tests; no broken requirements.
The original 54 tests remain, with fixtures migrated to explicit rules and the
new schema/copy. New tests exercise both input paths and rejection before the
engine factory is called.

Coverage includes captures, immediate ko, legal recapture after intervening moves,
single/multi-stone suicide, passes, wrong turns, root moves, BOM/UTF-8, escaped
metadata, duplicate/unsupported properties, collections/trailing junk, missing
metadata, strict JSON, nonfinite values and byte/node/move-count boundaries.
Chunked request size checks do not rely on Content-Length. Engine protocol mocks
verify rules, zero komi and distinct pass/current-position behavior.

## Installation Evidence

Verified on macOS arm64, Python 3.14.4. Both editable installation and normal
wheel installation succeeded. The clean environment was created outside the
repository at `/private/tmp/go-review-m1-clean-20260827`.

An import/API smoke test run from `/private/tmp` confirmed imports came from the
installed wheel, not the working tree. Wheel contents exclude archive, samples,
tests, frontend and docs. Installed API analysis with an explicit mock returned
review schema 2.1. Other Python/platform combinations are not yet verified.

## Browser Evidence

Checked with the in-app browser against localhost:3000 and a loopback-only
FastAPI service with real-engine environment variables deliberately unset.
This is an explicit mock-engine test, not a KataGo accuracy test.

- Missing manual metadata displays a clear message without analysis.
- Selecting Chinese rules/7.5 komi and entering two moves completes an API request.
- Uploading the synthetic sample uses its Japanese rules/6.5 komi even when
  different fallback controls are selected.
- The upload reports the first-variation-only warning and stored-result status.
- Desktop 1280x1000 and mobile 390x844 screenshots show the board and metadata
  controls without overlapping or overflowing their containers.

These are browser smoke checks, not a committed end-to-end browser test suite.
Comprehensive navigation, cancellation and live-engine browser acceptance remain M4.

## Remaining Boundaries

M1 was reverified (173 passed) and uploaded on 2026-08-27 after permission recovery.
Remote main and codex/m1-input-contract both resolved to d08fc47; the archive tag
was also uploaded. The existing Pages site has not changed.

At M1 acceptance, M2 still needed to remove default mock fallback, correct missing candidate/PV values
and score perspective, reuse the engine process and run genuine model-backed
tests/benchmarks. M3 must remove unsupported teaching claims. M4 owns complete
manual pass/input UX, preview confirmation and bounded analysis jobs. M5 owns
public backend hosting and second-device acceptance.

Input details and intentional rejections are defined in
[the contract](INPUT_CONTRACT.md). Authentication help is in
[the GitHub guide](GITHUB_AUTH.md).
