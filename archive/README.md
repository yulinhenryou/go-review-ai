# Prototype Archive

Historical material only. Nothing here is a runtime dependency, default report,
test fixture, or GitHub Pages asset. Current supported entry points remain in
`src/`, `app/`, and `frontend/` until their planned replacements are verified.

## Archived Output Snapshots

Moved on 2026-08-27, without changing their contents:

| Original path | Archived path | Reason |
| --- | --- | --- |
| `samples/sample_review_report.txt` | [legacy-reports/sample_review_report.txt](legacy-reports/sample_review_report.txt) | Stale generated teaching report; not verified real-engine evidence |
| `samples/sample_review_result.json` | [legacy-reports/sample_review_result.json](legacy-reports/sample_review_result.json) | Historical schema 2.0 snapshot; no current consumer or engine provenance |

Do not regenerate or update these snapshots to match the current application.
Their original context is commit `7447f54`. New regression fixtures should be
small, intentional, and stored with the tests that consume them.

## Source Archive

The [prototype baseline commit](https://github.com/yulinhenryou/go-review-ai/tree/7447f54688f45d3783e41b633663e760a8aa061e)
preserves the full prototype, including its CLI, API, board, mock engine and
teaching experiments. Tag `archive/prototype-2026-08-27` also points to this commit
and was uploaded after terminal authentication was restored on 2026-08-27.
Inspect the local tag without modifying the working tree:

```bash
git show archive/prototype-2026-08-27:src/katago_client.py
git show archive/prototype-2026-08-27:frontend/index.html
```

M2 moved mock behavior exclusively to test fixtures. M3 retired `src/classifier.py`,
`src/key_points.py`, `src/chinese_explanations.py` and `src/user_facing_labels.py`,
with their obsolete consumers/tests, from production and packaging. Their source
is retained in the prototype tag and pre-M3 commits, not duplicated here.
See the [report contract](../docs/REPORT_CONTRACT.md) and [roadmap](../docs/ROADMAP.md).

## Archive Rules

- No imports or default data loading from `archive/`.
- No copying archived artifacts into `frontend/` or release bundles.
- Preserve original paths, provenance and reasons in this index.
- Do not store secrets, model weights, uploads or runtime logs here.
- Use Git history/tags for retired code instead of keeping duplicate code trees.
