# M4 Job and Browser Contract

One application instance, one engine-owning worker, in-memory storage. This is a
local workflow milestone, not a multi-user public deployment or durable queue.
Input and report semantics remain in [INPUT_CONTRACT.md](INPUT_CONTRACT.md) and
[REPORT_CONTRACT.md](REPORT_CONTRACT.md).

## Endpoints

| Method and path | Behavior |
| --- | --- |
| `POST /api/v1/parse-sgf` | Parse/validate an upload and return preview plus every replay snapshot; no engine |
| `POST /api/v1/validate-moves` | Equivalent manual preview, including snapshots; no engine |
| `POST /api/v1/replay-moves` | Same preview contract, used for every proposed manual move/pass |
| `POST /api/v1/jobs` | Validate a complete canonical game, return HTTP 202 with a job ID |
| `GET /api/v1/jobs/{id}` | State, progress, error and final report if available |
| `GET /api/v1/jobs/{id}/input` | The job's immutable input as a replay preview, for page refresh recovery |
| `DELETE /api/v1/jobs/{id}` | Request cancellation; idempotent for retained terminal jobs |

Submission accepts the same strict fields as `analyze-moves`, plus optional
`input_warnings: ["first_variation_only"]`. Do not send preview-only
`record_status`, `positions`, `status` or `missing_fields`. Only that known input
warning is accepted; clients cannot provide engine evidence or reports.

The synchronous `analyze-sgf`, `analyze-moves` and expensive `/ready` endpoints
remain for compatibility. They use the same capacity/worker and deadline, not a
second unbounded engine path. `/health` never waits for an engine slot.

Example job view (job schema 1.0; report schema remains 3.0):

```json
{
  "schema_version": "1.0",
  "id": "opaque-random-id",
  "state": "running",
  "cancel_requested": false,
  "progress": {"completed": 16, "total": 21},
  "queue_position": 0,
  "retention_seconds": 1800,
  "result": null,
  "error": null
}
```

States are `queued`, `running`, `succeeded`, `failed`, `cancelled`. Queue position
is one-based while queued, zero otherwise. Progress counts completed analysis
positions including the final next-player position: N recorded moves -> N+1.
Real progress advances after each batch of up to 16 positions, including any
needed forced actual-move searches. Model loading and partial batches may leave
the count at zero; there is no invented time-based percentage.

`succeeded` means a report was produced, not that every evaluation is available.
The report may still be `status=partial`; coverage/nulls and quality notes remain
visible. Failed/cancelled jobs never expose a fabricated completed report.

## Bounds and Ownership

| Setting | Default | Permitted range |
| --- | ---: | --- |
| `GO_REVIEW_QUEUE_CAPACITY` | 2 waiting, plus 1 active | 0-8 waiting |
| `GO_REVIEW_JOB_TIMEOUT` | 900 seconds | >0, <=3600 |
| `GO_REVIEW_RESULT_TTL` | 1800 seconds after termination | >0, <=86400 |

The 900-second initial ceiling is conservative relative to the named-hardware
[235-move benchmark](M1_M3_REGRESSION.md); it is not a latency guarantee or a
promise that all 500-move records finish at every engine budget.

- Queue wait counts toward the deadline. Expired queued work fails before
  engine creation when its slot is reached.
- One worker owns creation, communication, termination and reaping of KataGo.
  Running cancellation remains `running` with `cancel_requested=true` until
  cleanup returns. Capacity is not released while the child is still alive.
- Checkpoints run during model hashing, before batches and in pipe polling
  (at most 250 ms between polling checkpoints). Cleanup waits up to two seconds
  after terminate, then kills and waits up to two more seconds if necessary.
- Queued cancellation immediately removes that queue entry. Shutdown cancels
  queued/running work, joins the worker and discards the store.
- Retain at most 16 terminal jobs and 32 MiB of serialized results, with an
  8 MiB per-result cap. Older terminal jobs may be evicted before the TTL under
  storage pressure. Input lengths/body limits also bound active data.
- Expiry runs during store access and on the idle worker, approximately every
  half second. Raw upload bytes are not retained; canonical inputs expire with
  their jobs. Results and task IDs are sent with `Cache-Control: no-store`.

Do not run multiple Uvicorn workers/replicas: their memory stores and queues are
independent. A CLI run is a separate process and is not governed by the API queue.

## Errors and Recovery

| Condition | Response |
| --- | --- |
| Invalid input | Existing 400/413/422 structured input errors; no job or engine |
| Full capacity | HTTP 429 `queue_full`, `Retry-After: 2` |
| Unknown/expired/restarted ID | HTTP 404 `job_unavailable`; resubmit input |
| Engine cannot start | Job `failed`, error `engine_unavailable` |
| Job/engine deadline | Job `failed`, error `analysis_timeout` |
| Other analysis/protocol/storage failure | Job `failed`, error `analysis_failed` |

Status requests for retained failed jobs return HTTP 200 with the structured job
error. Legacy synchronous requests return 503 or 504. Public messages do not
contain engine diagnostics, model filesystem paths or raw input.

The browser retains only the current job ID in session storage, not the SGF or
report. Reloading retrieves that job's input and state/result. Editing, clearing
or importing another record invalidates pending UI responses and requests
cancellation of the previous job. Late submission IDs are cancelled as well.
If a network failure loses the submission response itself, the browser may not
know its ID; the bounded server deadline still applies. Abandonment cancellation
is best-effort during outages, not a promise of immediate remote cleanup.

If polling fails with a known ID, the UI offers reconnection. After service
restart, an open page can resubmit its current input; a newly loaded page with
only an expired ID must re-import or re-enter the record. This is intentionally
not durable game storage. Closing a tab does not guarantee server cancellation.

## Frontend and Origins

`index.html` is markup only. `app.mjs` coordinates preview/input/jobs;
`input-state.mjs` owns accepted input and revision checks; `api.mjs` owns HTTP;
`job-client.mjs` owns polling/recovery; `board-view.mjs` draws server snapshots;
`review-controller.mjs` and `report-view.mjs` own review navigation/presentation.
There is no browser-side capture/ko implementation or automatic mock fallback.

Upload first previews names, rules, komi, move count, recorded result and variation
warnings. Recorded SGF rules/komi are locked; only missing metadata can be filled.
Manual entry supports pass, undo, clear and optional player names. Confirmation
creates a stable input snapshot before submitting real analysis.

Same origin is the default. For a separately hosted frontend, set the empty
`api-base` meta value in `frontend/index.html` to an exact HTTPS origin such as
`https://review-api.example.org`. Paths, credentials and query strings are not
accepted. Configure the backend with a JSON list of exact browser origins:

```bash
export GO_REVIEW_ALLOWED_ORIGINS='["https://example.github.io"]'
```

Only explicit HTTPS origins or loopback HTTP origins are allowed; no wildcard.
CORS is not authentication. Job IDs are unguessable bearer-style identifiers,
not accounts or access control. Do not publish this instance without the M5
HTTPS, abuse/rate-limit, resource and deployment checks. The Pages branch has not
been updated by M4.
