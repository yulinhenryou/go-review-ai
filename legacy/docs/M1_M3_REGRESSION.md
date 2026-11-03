# M1-M3 Combined Regression

Date: 2026-08-28. Source branch: `codex/m3-factual-report`, based on M2 `aba1ee0`.
Scope: revalidate M1-M3 and the local workspace follow-up before source
synchronization to GitHub. No functional code changes were needed in this pass.

## Automated Results

Python: **276 passed, zero skipped, 42.54 seconds**, with the live engine enabled.
The following disjoint groups describe coverage, not additional test runs:

| Area | Passing cases | Coverage |
| --- | ---: | --- |
| M1 | 131 | SGF parsing, game replay/legality, metadata, limits and input API |
| M2 | 67 | Analyzer, protocol/process/adapter, recorded responses, readiness and 3 live engine/pass cases |
| M3 | 54 | Threshold selection, factual reports, coverage, report API and 2 real mistake-report reruns |
| Local workspace | 24 | Static/API routing, launcher lifecycle, responsive health during analysis and frontend wiring |

Frontend Node tests: **23 passed**: 8 rule/komi, 6 report and 9 board-marker cases.
Both the project environment and a fresh wheel environment passed `pip check`.
Earlier desktop/mobile browser evidence is retained in
[local workspace acceptance](LOCAL_WORKSPACE_ACCEPTANCE.md); this pass rechecked
the real HTTP endpoints rather than repeating those screenshots.

## Real Engine

Environment: macOS 26.6.2 arm64, Python 3.14.4, Apple M4 / 16 GiB.
KataGo 1.16.4 Metal, model `kata1-b18c384nbt-s9996604416-d4316597426`.
Model SHA-256:
`9d7a6afed8ff5b74894727e156f04f0cd36060a24824892008fbb6e0cba51f1d`.

- Two 200-visit M3 test reruns identified moves 1, 3 and 5 in the synthetic
  six-move sample, with genuine played-move evidence and matching candidate PVs.
- Real multipart SGF HTTP request: 200, schema 3.0, `engine_source=katago`,
  6/6 evaluated moves, mistakes 1/3/5. Observed request time: 15.24 seconds.
- Real manual JSON HTTP request: 200, same schema/provenance, 2/2 evaluated
  moves for Black K10 and White L10 under Chinese rules / 7.5 komi. No moves
  crossed the configured threshold. Observed request time: 9.06 seconds.
- Both API reports retain unfinished/unknown record status; complete evaluation
  coverage is not presented as proof that the game itself is finished.
- The CLI sample entry point completed real 200-visit analysis and printed a
  factual report with 4/4 coverage, source hashes and quality warnings.

The public 235-move benchmark was rerun at **32 visits**, not the service default:

| Positions | Forced evaluations | Engine processes | Wall time | Peak child RSS |
| ---: | ---: | ---: | ---: | ---: |
| 236 | 41 | 1 | 61.25 s | 623,362,048 bytes (594.5 MiB) |

This is a low-budget observation on the named hardware, not a latency or strength
guarantee. The public sample and provenance are documented in
[sample notes](../samples/README.md). Original M2 measurements remain unchanged.

## Installation and Repository Hygiene

A fresh source copy was built outside the checkout, so stale `build/` contents
could not reintroduce retired modules. The resulting wheel was installed with
pinned constraints into a separate virtual environment.

- Isolated Python (`-I`) verified imports came from the installed wheel.
- The wheel has 24 entries and contains only Python packages and distribution
  metadata, without retired heuristic/mock modules, archives, SGFs or models.
- Installed API health and SGF/manual previews passed; illegal input was rejected.
- With deliberately unavailable engine paths, installed analysis returned 503
  `engine_unavailable`, not a simulated report.
- Frontend/static assets still require a checkout, as documented in README.
- Temporary wheel, environment, XML report and raw HTTP/benchmark outputs are
  outside the repository. No private SGFs, model files or runtime logs are
  included in this source update.

## Reproduction

Activate the project environment and set real engine paths as in README:

```bash
RUN_KATAGO_INTEGRATION=1 python -m pytest -q -ra
node --test tests/frontend/*.test.mjs
python -m pip check
python -m scripts.benchmark_engine samples/benchmark_pro_game.sgf --visits 32 \
  --output /tmp/go-review-long-benchmark.json
python -m src.main
git diff --check
```

## Publication Boundary

Source synchronization targets `main` and `codex/m3-factual-report`, without
force-pushing or rewriting M1/M2 history. The repository currently has only the
GitHub-generated Pages deployment workflow, not an M1-M3 test workflow; the
passing results above are local tests, not a claim of green GitHub CI.

`gh-pages` remains unchanged. Public backend hosting, bounded analysis jobs,
cancellation and the full web-v1 release gates remain M4/M5 work.
