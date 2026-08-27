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
teaching experiments. The local tag `archive/prototype-2026-08-27` also points to
this commit; that tag has not been uploaded because terminal Git authentication
failed. The commit link above is already available on GitHub.
Inspect the local tag without modifying the working tree:

```bash
git show archive/prototype-2026-08-27:src/katago_client.py
git show archive/prototype-2026-08-27:frontend/index.html
```

No standalone unused Python module was identified in the current source inventory.
The mock engine, classifier and key-point heuristics are still coupled to active
code and tests. They are recorded as replacement work, not falsely labeled as
already removed. M2 will isolate mock behavior; M3 will retire unsupported
teaching from the production report. See the [roadmap](../docs/ROADMAP.md).

## Archive Rules

- No imports or default data loading from `archive/`.
- No copying archived artifacts into `frontend/` or release bundles.
- Preserve original paths, provenance and reasons in this index.
- Do not store secrets, model weights, uploads or runtime logs here.
- Use Git history/tags for retired code instead of keeping duplicate code trees.
