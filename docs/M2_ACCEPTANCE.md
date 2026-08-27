# M2 Acceptance Record

Date: 2026-08-27. Branch: `codex/m2-engine-reliability`.

## Prerequisite Closed

M1 was reverified with 173 passing tests. Terminal GitHub write access was checked
by actual pushes, not just read access. Remote main and codex/m1-input-contract
both resolved to d08fc47e46d7d71d3823cbcdf288823b6a47f849. The annotated prototype
archive tag was uploaded. No force pushes or Pages publication were used.

## Delivered

- Real-only engine factory and loaded-model readiness endpoint.
- One process/model load per game, batches of up to 16 positions.
- Nonblocking bounded JSONL with exact ID/turn/final-response matching.
- Explicit restricted search for absent actual moves, including pass.
- Fixed-black raw values, moving-player loss, genuine candidate-owned PVs.
- Missing values remain missing; old report fails closed on incomplete evidence.
- Engine/model/config provenance, visit counts, search-noise/quality warnings.
- Mock implementation confined to tests and excluded from the wheel.
- Schema 2.2 and minimal frontend PV/chart adaptation; no M3 rewrite.

See [engine contract](ENGINE_CONTRACT.md) for exact semantics and limitations.

## Verification

- Regular suite: **225 passed, 3 opt-in tests skipped**.
- Final combined run with the real engine enabled: **228 passed**, no skips.
- Opt-in live-engine suite: **3 passed**, covering real numeric/PV evidence and
  two consecutive passes under Japanese and Chinese rules.
- Captured real response replay checks the complete normalized result except
  elapsed time and generated IDs, with no local paths in the saved fixture.
- Process fixtures cover fragmented JSONL, out-of-order turns, interim replies,
  stderr pressure, warnings, malformed/nonfinite/oversized output, unknown IDs,
  duplicate/wrong turns, timeout, exit and process reaping.
- Fresh Python 3.14.4 environment: normal wheel install with constraints,
  pip check, regular tests, and import/API smoke from outside the repository.
  The wheel contains neither tests/mock fixtures nor scripts/archive/sample data.
- Browser SGF upload completed real analysis at the default 200 visits.
  Manual entry of two moves also completed real analysis through the API.
  Selecting candidate 2 displays its own PV, not candidate 1's PV.
  Mobile 390x844 layout has no horizontal overflow. Fixed-black chart fields
  and visible candidate data were checked. These are smoke checks, not M4's
  complete automated end-to-end acceptance suite.

Commands:

```bash
python -m pytest -q -ra
RUN_KATAGO_INTEGRATION=1 python -m pytest tests/test_katago_integration.py -q -ra
python -m scripts.benchmark_engine samples/sample_game.sgf --visits 32 \
  --record-public-fixture --output tests/fixtures/katago_real_short.json
python -m scripts.benchmark_engine samples/benchmark_pro_game.sgf --visits 32 \
  --output docs/evidence/m2-long-benchmark.json
```

Set the model/config environment as documented in README before real runs.

## Measured Performance

Hardware: Apple M4, 16 GiB unified memory. macOS 26.6.2 arm64, Python 3.14.4.
Engine: KataGo 1.16.4, Metal backend. Model:
`kata1-b18c384nbt-s9996604416-d4316597426`, SHA-256
`9d7a6afed8ff5b74894727e156f04f0cd36060a24824892008fbb6e0cba51f1d`.
Config: repository baseline, 2 analysis threads x 2 search threads, batch size 8.

| Input | Root budget | Positions | Forced searches | Cold-process wall time | Engine peak RSS | Processes |
| --- | --- | --- | --- | --- | --- | --- |
| Synthetic 4-move sample | 32 visits | 5 | 1 | 3.01 s | 610 MiB | 1 |
| Public 235-move game | 32 visits | 236 | 40 | 65.18 s | 620 MiB | 1 |

Sources: [short capture](../tests/fixtures/katago_real_short.json),
[long measurement](evidence/m2-long-benchmark.json),
[long-game provenance and metadata normalization](../samples/README.md).

These are individual low-budget observations, not latency guarantees or strength
benchmarks. Peak RSS is the OS-reported child process maximum; it is not total
system/GPU allocation. The default service uses 200 visits, so the table must not
be quoted as its response time. More hardware/budgets and quality calibration
are needed before setting production queue/timeout targets.

## Remaining Work

M2's integration gate is satisfied on the named local environment. This does
not certify the old report's tactical narratives or an online release.
M3 must replace heuristic teaching and add factual, coverage-aware reports.
M4 must add bounded jobs, cancellation, full manual pass controls and
complete frontend acceptance. M5 must provide a public backend and
second-device acceptance. Windows is not supported by this POSIX transport.
GitHub Pages remains the older static prototype, separate from main.
